import os
import time
import random
import json
import serial
import datetime
import subprocess
import re
import numpy as np
import ray
from ray import tune
from ray.rllib import agents
from pexpect import spawn, EOF

from flask import Flask, render_template, request, jsonify
from manuf import manuf

app = Flask(__name__)

hasOUILookup = False

try:
    from manuf import manuf
    hasOUILookup = True
except:
    hasOUILookup = False

def get_network_interfaces():
    result = os.popen('ip -o link show | awk \'{print $2}\'').read()
    interfaces = set(result.split('\n'))
    interfaces = [iface.rstrip(':') for iface in interfaces if iface.strip()]
    return interfaces

def get_serial_ports():
    ports = [f'/dev/{dev}' for dev in os.listdir('/dev') if dev.startswith('ttyACM') or dev.startswith('ttyUSB')]
    return ports

def send_command(ser, command):
    for char in command:
        ser.write(char.encode())
        time.sleep(0.01)
    ser.write(b'\r\n')
    
 # Constants
AZIMUTH_RANGE = (160, 6400)
ELEVATION_RANGE = (650, 1450)
MAC_ADDRESS = 'xx:xx:xx:xx:xx:xx'  # replace with the target MAC address
INTERFACE = 'wlan0'  # replace with the actual interface

class AntennaEnv(ray.rllib.env.MultiAgentEnv):
    def __init__(self, config):
        self.azim = np.random.randint(*AZIMUTH_RANGE)
        self.elev = np.random.randint(*ELEVATION_RANGE)
        self.signal_strength = self.get_signal_strength()
        self.command_child = spawn('bash')
        self.command_child.expect(EOF)

    def get_signal_strength(self):
        os.system(f"iwlist {INTERFACE} scan | grep -A 5 -B 5 '{MAC_ADDRESS}' > scan.txt")
        with open("scan.txt") as f:
            for line in f:
                if "Quality" in line:
                    # assuming signal quality format as 'Quality=XX/100'
                    return int(line.split("=")[1].split('/')[0])
        return 0

    def set_antenna(self, azim, elev):
        self.command_child.sendline(f'/send_commands azim {azim}')
        self.command_child.sendline(f'/send_commands elev {elev}')
        self.command_child.expect(EOF)

    def reset(self):
        self.azim = np.random.randint(*AZIMUTH_RANGE)
        self.elev = np.random.randint(*ELEVATION_RANGE)
        self.set_antenna(self.azim, self.elev)
        self.signal_strength = self.get_signal_strength()
        return [self.azim, self.elev, self.signal_strength]

    def step(self, action):
        self.azim += action[0]
        self.elev += action[1]
        self.set_antenna(self.azim, self.elev)
        time.sleep(1)  # wait for antenna to set and for scanning

        new_signal_strength = self.get_signal_strength()
        reward = new_signal_strength - self.signal_strength
        self.signal_strength = new_signal_strength

        return [self.azim, self.elev, self.signal_strength], reward, False, {}


ray.init()

trainer = agents.ppo.PPOTrainer(env=AntennaEnv, config={"framework": "torch"})

# Load from checkpoint if exists
checkpoint_path = "./checkpoint"  # Put your desired checkpoint path here
if os.path.exists(checkpoint_path):
    trainer.restore(checkpoint_path)

# Training loop
for i in range(10000):
    trainer.train()
    if i % 100 == 0:
        checkpoint = trainer.save(checkpoint_path)
        print(f"Checkpoint saved at {checkpoint}")

@app.route('/get_serial_ports', methods=['GET'])
def get_serial_ports_endpoint():
    return jsonify(get_serial_ports())

@app.route('/get_network_interfaces', methods=['GET'])
def get_network_interfaces_endpoint():
    return jsonify(get_network_interfaces())
    
@app.route('/')
def index():
    serial_ports = get_serial_ports()
    network_interfaces = get_network_interfaces()
    return render_template('index.html', serial_ports=serial_ports, network_interfaces=network_interfaces)

@app.route('/send_command', methods=['POST'])
def handle_send_command():
    port = request.form['port']
    command = request.form['command']
    
    ser = serial.Serial(port, 9600, timeout=1)
    send_command(ser, command)
    response = ser.read(1024).decode()
    ser.close()
    
    return jsonify(response=response)

@app.route('/iwlist', methods=['POST'])
def handle_iwlist():
    interface = request.form['interface']
    command = request.form['command']
    output = os.popen(f'sudo iwlist {interface} {command}').read()
    return jsonify(output=output)

@app.route('/start_scan', methods=['POST'])
def handle_start_scan():
    port = request.form['port']
    ser = serial.Serial(port, 9600, timeout=1)
    
    for azim in range(170, 6301, 3000):
        command = f'G1 X{azim}'
        send_command(ser, command)
        for elev in range(650, 1401, 500):
            command = f'G1 Y{elev}'
            send_command(ser, command)
    
    ser.close()
    return jsonify(success=True)

@app.route('/wifi_scan', methods=['POST'])
def handle_wifi_scan():
    interface = request.form['interface']
    output = os.popen(f'sudo iwlist {interface} scan').read()
    devices = parse_wifi_scan_output(output)
    return jsonify(devices=list(devices.values()))

def parse_wifi_scan_output(output):
    devices = {}
    lines = output.split('\n')

    p = manuf.MacParser()

    for index, line in enumerate(lines):
        if "Address" in line:
            mac = line.split()[-1]
            if mac in devices:
                continue

            device_data = {
                "mac": mac,
                "essid": extract_value(lines, index, "ESSID:\"(.*)\""),
                "mode": extract_value(lines, index, "Mode:(.*)"),
                "channel": extract_value(lines, index, "Channel:(.*)"),
                "frequency": extract_value(lines, index, "Frequency:(.*)"),
                "quality": extract_value(lines, index, "Quality=(.*)"),
                "signal": extract_value(lines, index, "Signal level=(.*)"),
                "noise": extract_value(lines, index, "Noise level=(.*)"),
                "encryption": extract_value(lines, index, "Encryption key:(.*)"),
                "device_type": p.get_manuf(mac) if p.get_manuf(mac) else None
            }

            devices[mac] = device_data

    return devices



def extract_value(lines, start_index, pattern):
    regex = re.compile(pattern)
    for i in range(start_index + 1, len(lines)):
        match = regex.search(lines[i])
        if match:
            return match.group(1)
    return None

@app.route('/array_scan', methods=['POST'])
def handle_array_scan():
    port = request.form['port']
    ser = serial.Serial(port, 9600, timeout=1)
    
    azim_min = 170
    azim_max = 6301
    elev_min = 650
    elev_max = 1401
    step = 500

    direction = 1
    for azim in range(azim_min, azim_max + 1, step):
        command = f'azim {azim}'
        send_command(ser, command)
        time.sleep(2)  # Pause for two seconds

        elev_values = list(range(elev_min, elev_max + 1, step))
        if direction == -1:
            elev_values = elev_values[::-1]  # Reverse the order of the elevations
        for elev in elev_values:
            command = f'elev {elev}'
            send_command(ser, command)
            time.sleep(2)  # Pause for two seconds
        
        direction *= -1

    ser.close()
    return jsonify(success=True)




if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

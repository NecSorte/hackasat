import os
import time
import random
import json
import serial
import datetime
import subprocess
import re
import numpy as np
from threading import Thread

from flask import Flask, render_template, request, jsonify
from manuf import manuf

app = Flask(__name__)

known_devices = {}  # Global known devices dictionary

# Constants
AZIMUTH_RANGE = (160, 6400)
ELEVATION_RANGE = (650, 1450)

# Q-Learning parameters
alpha = 0.5
gamma = 0.95
epsilon = 0.1
state_space = 10
action_space = 4
q_table = np.zeros((state_space, action_space))

# Global state
current_state = 0
should_stop = False

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
            if mac in devices:  # Skip if device already added
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
                "device_type": p.get_manuf(mac)
            }

            devices[mac] = device_data

            # Update the known devices dictionary
            known_devices[mac] = device_data

    return devices


def extract_value(lines, start_index, pattern):
    regex = re.compile(pattern)
    for i in range(start_index + 1, len(lines)):
        match = regex.search(lines[i])
        if match:
            return match.group(1)
    return None

# Define the function to continuously track a device
def track_device(mac_address):
    global should_stop, current_state, known_devices
    device = known_devices.get(mac_address)
    if device is None:
        return
    while not should_stop:
        # Choose action
        if random.uniform(0, 1) < epsilon:
            action = np.random.choice(action_space)  # Explore action space
        else:
            action = np.argmax(q_table[current_state])  # Exploit learned values

        # Take action and get reward
        azim, elev = adjust_antenna(current_state, action)
        os.system(f"/send_commands azim {azim}")
        os.system(f"/send_commands elev {elev}")
        time.sleep(1)  # Wait for a bit before checking again

        # Find the device in the known_devices array
        device = next((dev for dev in known_devices.values() if dev['mac'] == mac_address), None)
        if device is None:
            continue
        
        # Get the new signal strength from the device
        new_signal_strength = device.get('signal')
        reward = new_signal_strength if new_signal_strength else -100

        # Update Q-table
        old_value = q_table[current_state, action]
        next_max = np.max(q_table[current_state])
        
        new_value = (1 - alpha) * old_value + alpha * (reward + gamma * next_max)
        q_table[current_state, action] = new_value

        # Update current state
        current_state = int(azim / ((AZIMUTH_RANGE[1] - AZIMUTH_RANGE[0]) / state_space))

# Function to get the new position of the antenna based on the current state and action
def adjust_antenna(state, action):
    azim = state * ((AZIMUTH_RANGE[1] - AZIMUTH_RANGE[0]) / state_space)
    elev = ELEVATION_RANGE[0] if action < 2 else ELEVATION_RANGE[1]
    if action % 2 == 1:
        azim += (AZIMUTH_RANGE[1] - AZIMUTH_RANGE[0]) / state_space
    return azim, elev

# Route to start tracking
# Update the /track_device route to track one MAC address
@app.route('/track_device', methods=['POST'])
def start_tracking():
    global should_stop
    should_stop = False
    mac_address = request.form.get('mac_address')
    if mac_address is None:
        return jsonify(success=False, message="mac_address is required"), 400

    device = known_devices.get(mac_address)
    if device is None:
        return jsonify(success=False, message="Device not found"), 404

    Thread(target=track_device, args=(mac_address,)).start()  # Track the MAC address

    return jsonify(success=True)

@app.route('/stop_tracking', methods=['POST'])
def stop_tracking():
    global should_stop
    should_stop = True
    return jsonify(success=True)



@app.route('/array_scan', methods=['POST'])
def handle_array_scan():
    port = request.form['port']
    ser = serial.Serial(port, 9600, timeout=1)
    
    azim_min = 170
    azim_max = 6301
    elev_min = 650
    elev_max = 1401
    step = 500

    for azim in range(azim_min, azim_max + 1, step):
        command = f'G1 X{azim}'
        send_command(ser, command)
        for elev in range(elev_min, elev_max + 1, step):
            command = f'G1 Y{elev}'
            send_command(ser, command)

    ser.close()
    return jsonify(success=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

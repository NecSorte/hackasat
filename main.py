import os
import time
import random
import json
import serial
import datetime
import subprocess
import re
import threading
import numpy as np
from threading import Thread
from queue import Queue

from flask import Flask, render_template, request, jsonify
from manuf import manuf
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(2)

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

# Function to extract signal strength from iwlist output
def parse_signal_strength(output):
    m = re.search('Signal level=(-?\d+)', output)
    return int(m.group(1)) if m else None

# Function to get the new position of the antenna based on the current state and action
def adjust_antenna(state, action):
    azim = state * ((AZIMUTH_RANGE[1] - AZIMUTH_RANGE[0]) / state_space)
    elev = ELEVATION_RANGE[0] if action < 2 else ELEVATION_RANGE[1]
    if action % 2 == 1:
        azim += (AZIMUTH_RANGE[1] - AZIMUTH_RANGE[0]) / state_space
    return azim, elev

def track_device(mac_address):
    global should_stop, current_state
    while not should_stop:
        # Choose action
        if random.uniform(0, 1) < epsilon:
            action = np.random.choice(action_space)  # Explore action space
        else:
            action = np.argmax(q_table[current_state])  # Exploit learned values

        # Take action and get reward
        azim, elev = adjust_antenna(current_state, action)
        send_command(ser, f"azim {azim}")
        send_command(ser, f"elev {elev}")
        time.sleep(1)  # Wait for a bit before checking again

        output = os.popen(f"iwlist {INTERFACE} scan | grep -A5 '{mac_address}' | grep 'Signal level'").read()
        new_signal_strength = parse_signal_strength(output)
        reward = new_signal_strength if new_signal_strength else -100

        # Update Q-table
        old_value = q_table[current_state, action]
        next_max = np.max(q_table[current_state])
        
        new_value = (1 - alpha) * old_value + alpha * (reward + gamma * next_max)
        q_table[current_state, action] = new_value

        # Update current state
        current_state = int(azim / ((AZIMUTH_RANGE[1] - AZIMUTH_RANGE[0]) / state_space))

def start_scan(port):
    ser = serial.Serial(port, 9600, timeout=1)
    
    for azim in range(170, 6301, 3000):
        command = f'G1 X{azim}'
        send_command(ser, command)
        for elev in range(650, 1401, 500):
            command = f'G1 Y{elev}'
            send_command(ser, command)
    
    ser.close()
    return jsonify(success=True)
   
def array_scan(port):
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

    
# Route to start tracking
@app.route('/track_device', methods=['POST'])
def start_tracking():
    global should_stop
    should_stop = False
    mac_address = request.form['mac_address']
    threading.Thread(target=track_device, args=(mac_address,)).start()
    return jsonify(success=True)

# Route to stop tracking
@app.route('/stop_tracking', methods=['POST'])
def stop_tracking():
    global should_stop

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
    
    try:
        ser = serial.Serial(port, 9600, timeout=1)
        send_command(ser, command)
        time.sleep(1) # add delay
        response = ser.read(1024).decode()
        ser.close()
    except SerialException as e:
        return jsonify(error=str(e)), 500
    
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
    executor.submit(start_scan, port)
    return jsonify(success=True)

@app.route('/wifi_scan', methods=['POST'])
def handle_wifi_scan():
    interface = request.form['interface']
    executor.submit(wifi_scan, interface)
    output = os.popen(f'sudo iwlist {interface} scan').read()
    devices = parse_wifi_scan_output(output)
    time.sleep(1)  # pause execution for 1 second
    return jsonify(devices=list(devices.values()))

def wifi_scan(interface, known_devices):
    output = os.popen(f'sudo iwlist {interface} scan').read()
    devices = parse_wifi_scan_output(output, known_devices)
    time.sleep(1)  # pause execution for 1 second
    return jsonify(devices=list(devices.values()))

def parse_wifi_scan_output(output, known_devices):
    lines = output.split('\n')

    p = manuf.MacParser()

    for index, line in enumerate(lines):
        if "Address" in line:
            mac = line.split()[-1]

            # If the mac is in known devices, update the device's data
            if mac in known_devices:
                known_devices[mac]['essid'] = extract_value(lines, index, "ESSID:\"(.*)\"")
                known_devices[mac]['mode'] = extract_value(lines, index, "Mode:(.*)")
                known_devices[mac]['channel'] = extract_value(lines, index, "Channel:(.*)")
                known_devices[mac]['frequency'] = extract_value(lines, index, "Frequency:(.*)")
                known_devices[mac]['quality'] = extract_value(lines, index, "Quality=(.*)")
                known_devices[mac]['signal'] = extract_value(lines, index, "Signal level=(.*)")
                known_devices[mac]['noise'] = extract_value(lines, index, "Noise level=(.*)")
                known_devices[mac]['encryption'] = extract_value(lines, index, "Encryption key:(.*)")
                known_devices[mac]['device_type'] = p.get_manuf(mac) if p.get_manuf(mac) else None
            else:
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

                known_devices[mac] = device_data

    return known_devices



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
    
    try:
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
            time.sleep(1)  # Pause for one second

            elev_values = list(range(elev_min, elev_max + 1, step))
            if direction == -1:
                elev_values = elev_values[::-1]  # Reverse the order of the elevations
            for elev in elev_values:
                command = f'elev {elev}'
                send_command(ser, command)
                time.sleep(1)  # Pause for one second
        
            direction *= -1

        ser.close()
    except SerialException as e:
        return jsonify(error=str(e)), 500

    return jsonify(success=True)



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

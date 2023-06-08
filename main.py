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
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

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

# Define a lock
lock = threading.Lock()

# Define the known devices dictionary
known_devices = {}

# Define the set of seen MAC addresses
seen_mac_addresses = set()

def add_or_update_device(new_device):
    # Acquire the lock before accessing known_devices
    with lock:
        # Check if we've seen this MAC address before
        if new_device['mac'] in seen_mac_addresses:
            # The device already exists in the dictionary. Update it.
            existing_device = known_devices.get(new_device['mac'])

            # Update fields in existing_device if they are present in new_device
            for field in ['ssid', 'signal', 'channel', 'lastSeen', 'encryption', 'frequency']:
                existing_device[field] = new_device.get(field, existing_device.get(field, None))
        else:
            # This is a new device. Add it to the dictionary.
            if all(key in new_device for key in ['ssid', 'signal', 'channel', 'lastSeen', 'encryption', 'frequency']):
                known_devices[new_device['mac']] = new_device
                # Add the MAC address to the set of seen MAC addresses
                seen_mac_addresses.add(new_device['mac'])
            else:
                missing_keys = [key for key in ['ssid', 'signal', 'channel', 'lastSeen', 'encryption', 'frequency'] if key not in new_device]
                print(f"Warning: Cannot add new_device to known_devices due to missing keys: {missing_keys}")

# Define the function that reads known_devices
def get_known_devices():
    # Acquire the lock before accessing known_devices
    with lock:
        # Do stuff with known_devices here
        return known_devices.copy()  # Return a copy of the known_devices dictionary

has_oui_lookup = False

try:
    from manuf import manuf
    has_oui_lookup = True
except ImportError:
    has_oui_lookup = False

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

# Function to continuously track a device
def track_device(device):
    global should_stop, current_state, allDevices
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

        # Find the device in the allDevices array
        device = next((dev for dev in allDevices if dev['mac'] == device['mac']), None)
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

# Route to start tracking
# Update the /track_device route to track one MAC address
@app.route('/track_device', methods=['POST'])
def start_tracking():
    global should_stop
    should_stop = False
    mac_address = request.form.get('mac_address')
    if mac_address is None:
        return jsonify(success=False, message="mac_address is required"), 400
    
    devices = get_known_devices()
    device = next((dev for dev in devices if dev['mac'] == mac_address), None)
    if device is None:
        return jsonify(success=False, message="Device not found"), 404
    
    Thread(target=track_device, args=(mac_address,)).start()  # Track the MAC address
    
    return jsonify(success=True)

@app.route('/stop_tracking', methods=['POST'])
def stop_tracking():
    global should_stop
    should_stop = True
    return jsonify(success=True)
    
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
    try:
        interface = request.form['interface']
        print(f"Scanning on interface: {interface}")  # Debug line
        output = os.popen(f'sudo iwlist {interface} scan').read()
        print(output[:100])  # Debug line, print the first 100 characters of the output
        devices = parse_wifi_scan_output(output)
        for device in devices.values():
            add_or_update_device(device)
        print(jsonify(devices=list(get_known_devices().values())))  # Debug line, 
        return jsonify(devices=list(get_known_devices().values()))
    except Exception as e:
        print(e)  # Debug line
        return jsonify(error=str(e)), 500

def extract_value_for_key(lines, start_index, key):
    for i in range(start_index + 1, len(lines)):
        if key in lines[i]:
            return lines[i].split(":")[-1].strip()
    return None

def parse_wifi_scan_output(output):
    devices = {}
    lines = output.split('\n')

    for index, line in enumerate(lines):
        if "Address" in line:
            address = line.split()[-1]
            if address in devices:
                continue

            device_data = {
                "Address": address,
                "ESSID": extract_value_for_key(lines, index, "ESSID"),
                "Protocol": extract_value_for_key(lines, index, "Protocol"),
                "Mode": extract_value_for_key(lines, index, "Mode"),
                "Frequency": extract_value_for_key(lines, index, "Frequency"),
                "Encryption key": extract_value_for_key(lines, index, "Encryption key"),
                "IE": extract_value_for_key(lines, index, "IE:"),
                "Quality": extract_value_for_key(lines, index, "Quality"),
                "Signal level": extract_value_for_key(lines, index, "Signal level"),
            }
            devices[address] = device_data

    return devices

@app.route('/array_scan', methods=['POST'])
def handle_array_scan():
    port = request.form['port']
    ser = serial.Serial(port, 9600, timeout=1)
    
    azim_min = 170
    azim_max = 6301
    elev_min = 650
    elev_max = 1401
    step = 200

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
    return jsonify(success=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

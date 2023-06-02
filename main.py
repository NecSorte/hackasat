import os
import time
import random
import json
import serial
import datetime
import subprocess
import re
import threading
import math
import requests

from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

hasOUILookup = False

try:
    from manuf import manuf
    hasOUILookup = True
except:
    hasOUILookup = False

ELK_LOGSTASH_URL = 'http://localhost:5044'  # Replace with your Logstash URL

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

# Shared variable for controlling tracking thread
should_stop = False

# Function to extract signal strength from iwlist output
def parse_signal_strength(output):
    m = re.search('Signal level=(-?\d+)', output)
    return int(m.group(1)) if m else None

# Function to get the new position of the antenna based on the current signal strength
def adjust_antenna(current_signal_strength):
    # These values would need to be determined based on your specific antenna and environment
    min_signal_strength = -100
    max_signal_strength = 0
    min_azimuth = 160
    max_azimuth = 6400
    min_elevation = 650
    max_elevation = 1400

    # Normalize the signal strength to a value between 0 and 1
    normalized_strength = (current_signal_strength - min_signal_strength) / (max_signal_strength - min_signal_strength)

    # Determine the new azimuth and elevation based on the normalized signal strength
    new_azimuth = min_azimuth + normalized_strength * (max_azimuth - min_azimuth)
    new_elevation = min_elevation + math.sqrt(normalized_strength) * (max_elevation - min_elevation)

    return new_azimuth, new_elevation

# Function to continuously track a device
def track_device(mac_address, interface='wlan0'):
    global should_stop
    while not should_stop:
        # Use iwlist to get the current signal strength
        output = os.popen(f"iwlist {interface} scan | grep -A5 '{mac_address}' | grep 'Signal level'").read()
        current_signal_strength = parse_signal_strength(output)

        # Adjust the antenna based on the current signal strength
        new_azimuth, new_elevation = adjust_antenna(current_signal_strength)

        # Send the new azimuth and elevation to the antenna
        ser.write(f"azim {new_azimuth}\n")
        ser.write(f"elev {new_elevation}\n")

        # Wait for a bit before checking again
        time.sleep(1)

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
    return render_template('index.html')

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
    send_devices_to_logstash(devices)
    return jsonify(devices=list(devices.values()))

def parse_wifi_scan_output(output):
    devices = {}
    lines = output.split('\n')

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

def send_devices_to_logstash(devices):
    headers = {'Content-Type': 'application/json'}
    for device in devices.values():
        requests.post(ELK_LOGSTASH_URL, json=device, headers=headers)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

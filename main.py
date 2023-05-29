import os
import time
import random
import json
import serial
import datetime
import subprocess
import re

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
    interfaces = result.split('\n')
    return [iface.strip(" :") for iface in interfaces if iface]

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
    return jsonify(devices=devices)

def parse_wifi_scan_output(output):
    devices = {}
    lines = output.split('\n')

    p = manuf.MacParser()

    regexes = {
        'mac': re.compile(r'Address: (.*)'),
        'essid': re.compile(r'ESSID:"(.*)"'),
        'mode': re.compile(r'Mode:(.*)'),
        'channel': re.compile(r'Channel:(\d+)'),
        'frequency': re.compile(r'Frequency:(\d+\.\d+) GHz'),
        'quality': re.compile(r'Quality=(\d+)/\d+'),
        'signal': re.compile(r'Signal level=(\-?\d+) dBm'),
        'noise': re.compile(r'Noise level=(\-?\d+) dBm')
    }

    encryption_regexes = {
        'WEP': re.compile(r'Encryption key:on'),
        'WPA': re.compile(r'IE: WPA Version 1'),
        'WPA2': re.compile(r'IE: IEEE 802.11i/WPA2 Version 1'),
        'WPA2 Enterprise': re.compile(r'IE: IEEE 802.11i/WPA2 Version 1\n.*Authentication Suites \(1\) : 802\.1x'),
        'WPA3': re.compile(r'IE: IEEE 802.11i/WPA2 Version 3'),
        'WPA Enterprise': re.compile(r'IE: WPA Version \d+\n.*Authentication Suites \(1\) : 802\.1x'),
    }

    device = {}
    for line in lines:
        for key, regex in regexes.items():
            match = regex.search(line)
            if match:
                device[key] = match.group(1)

        if 'Encryption key:off' in line:
            device['encryption'] = 'Open'
        else:
            for enc_type, regex in encryption_regexes.items():
                if regex.search(output):
                    device['encryption'] = enc_type
                    break

        # When a new cell is detected, save the previous device and create a new one
        if line.startswith('Cell'):
            if 'mac' in device:
                device['device_type'] = p.get_manuf(device.get('mac', ''))
                devices[device['mac']] = device
            device = {}

    # Don't forget to add the last device
    if 'mac' in device:
        device['device_type'] = p.get_manuf(device.get('mac', ''))
        devices[device['mac']] = device

    return list(devices.values())



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

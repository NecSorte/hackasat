import os
import time
import random
import json
import serial
import datetime
import subprocess

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
    devices = []
    lines = output.split('\n')

    p = manuf.MacParser()
    
    for index, line in enumerate(lines):
        if "Address" in line:
            mac = line.split()[-1]
            ssid = essid = ""

            for i in range(index + 1, len(lines)):
                if "ESSID" in lines[i]:
                    essid = lines[i].split('"')[1]
                    break

            for i in range(index + 1, len(lines)):
                if "Quality" in lines[i]:
                    ssid = lines[i].split()[-1]
                    break

            device_type = p.get_manuf(mac)
            devices.append({
                "mac": mac,
                "ssid": ssid,
                "essid": essid,
                "device_type": device_type
            })

    return devices

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

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

# There are some "plugins" that are available for addons.  Let's see if they're present
hasFalcon = False
hasBluetooth = False
hasUbertooth = False

try:
    from manuf import manuf
    hasOUILookup = True
except:
    hasOUILookup = False
    
#oui db function 
def getOUIDB():
    ouidb = None
    
    if hasOUILookup:
        if  os.path.isfile('manuf'):
            # We have the file but let's not update it every time we run the app.
            # every 90 days should be plenty
            last_modified_date = datetime.datetime.fromtimestamp(os.path.getmtime('manuf'))
            now = datetime.datetime.now()
            age = now - last_modified_date
            
            if age.days > 90:
                updateflag = True
            else:
                updateflag = False
        else:
            # We don't have the file, let's get it
            updateflag = True
            
        try:
            ouidb = manuf.MacParser(update=updateflag)
        except:
            print("Error updating the MAC address database.  Please check if the manuf module needs updating with 'sudo pip3 install --upgrade manuf'.")
            ouidb = None
    else:
        ouidb = None
        
    return ouidb

# auto bind usb devices found. 
def bind_usb_devices():
    try:
        output = subprocess.check_output("usbip list -l", shell=True).decode("utf-8")
        devices = [line.strip() for line in output.split("\n") if "busid" in line]

        for device in devices:
            busid = device.split(" ")[1]
            print(f"Binding USB device with busid: {busid}")
            subprocess.run(f"sudo usbip bind --busid={busid}", shell=True)
    except Exception as e:
        print(f"Error while binding USB devices: {e}")

# Call the function to bind the USB devices
bind_usb_devices()

# lookup serial ports. Specifically any AMC. Needs further testing...) 
def get_serial_ports():
    ports = [f'/dev/{dev}' for dev in os.listdir('/dev') if dev.startswith('ttyACM') or dev.startswith('ttyUSB')]
    return ports

# lookup wireless devicees
def get_wireless_interfaces():
    result = os.popen('iwconfig 2>&1 | grep "^[^ ]" | awk \'{print $1}\'').read()
    interfaces = result.split('\n')
    return [iface for iface in interfaces if iface]

# tty device only processes one char at a time. time.sleep(0.01) works. looking to lower the delay moving forward. 
def send_command(ser, command):
    for char in command:
        ser.write(char.encode())
        time.sleep(0.01)
    ser.write(b'\r\n')

@app.route('/')
def index():
    serial_ports = get_serial_ports()
    wireless_interfaces = get_wireless_interfaces()
    return render_template('index.html', serial_ports=serial_ports, wireless_interfaces=wireless_interfaces)

@app.route('/send_command', methods=['POST'])
def handle_send_command():
    port = request.form['port']
    command = request.form['command']
    
    ser = serial.Serial(port, 9600, timeout=1)
    send_command(ser, command)
    response = ser.read(1024).decode()
    ser.close()
    
    return jsonify(response=response)

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
                    ssid = lines[i].split('"')[1]
                    break

            for i in range(index + 1, len(lines)):
                if "Quality" in lines[i]:
                    essid = lines[i].split()[-1]
                    break

            device_type = p.get_manuf(mac)
            devices.append({"mac": mac, "ssid": ssid, "essid": essid, "device_type": device_type})

    return devices

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

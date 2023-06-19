# Antenna Tracker Application

This application enables you to track and scan for Wi-Fi signals from a particular device, move your antenna to optimal positions, and interact with the antenna directly. The application uses Flask for the backend, and uses the `iwlist` command on Linux to scan for Wi-Fi signals.

## Features:

- Scan for Wi-Fi signals
- Interact with the antenna directly via a serial port
- Move the antenna to different azimuth and elevation angles to optimize signal quality
- Track a specific device by its MAC address

## Requirements

- Python 3.6+
- Ubuntu Lite OS / Tested on Kali 
- `iwlist` command (part of the wireless-tools package in Ubuntu)

## Installation Guide

1. Clone the repository:
    ```
    git clone https://github.com/necsorte/hackasat.git
    cd antenna-tracker
    ```
2. Install the necessary system dependencies:
    ```
    sudo apt-get update && sudo apt-get install -y python3-pip python3-dev gcc libpq-dev wireless-tools
    ```
3. Install the required Python libraries:
    ```
    sudo pip3 install -r requirements.txt
    ```
4. Run the application:
    ```
    python3 main.py
    ```

The application should now be running on your local machine at `http://localhost:5000`.

## Usage

- Access the application on your browser at `http://localhost:5000`.
- Use the provided interface to interact with your antenna and perform scans.
- You can also use the available REST API endpoints for a more programmatic interaction.


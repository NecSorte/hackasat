# WiFi Tracker Project

This project focuses on creating a WiFi tracker using Python, Flask, Docker, and Kali Linux. It's a tool designed to monitor and analyze the WiFi networks around you. 

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

1. Docker
2. Python 3
3. Pip (Python package installer)
4. Git
5. A machine running Kali Linux or a similar distribution

### Installation

1. Clone the repository to your local machine:
   ```
   git clone https://github.com/username/wifi-tracker.git
   ```
2. Navigate to the project directory:
   ```
   cd wifi-tracker
   ```
3. Build the Docker image:
   ```
   docker build -t wifi-tracker .
   ```
4. Run the Docker container:
   ```
   docker run -d -p 5000:5000 wifi-tracker
   ```

### Usage

Navigate to `http://localhost:5000` on your web browser to access the application.

## Features

1. WiFi network scanning.
2. Display network details, such as SSID, signal strength, and security type.
3. Ability to use USB devices from the host machine within the Docker container using the USBIP protocol.
4. Flask web application for user interaction.

## Contribution

If you wish to contribute to this project, please fork the repository and submit a pull request.

## Disclaimer

This tool is for educational purposes only. Unauthorized network scanning can violate privacy laws and terms of service. Always seek permission before accessing any network other than your own.

## License

This project is licensed under the MIT License. See the LICENSE file for details.

## Acknowledgments

Thanks to everyone who contributed to this project. Your efforts have helped in creating a tool that will benefit many developers and network enthusiasts.

---

For more details, please refer to the project documentation. If you have any questions or issues, feel free to open an issue on the project's GitHub page.

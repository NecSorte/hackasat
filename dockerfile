# Use the Kali Linux base image
FROM kalilinux/kali-rolling

# Update package list and install required packages
RUN apt-get update && apt-get install -y git && \
    apt-get install -y --no-install-recommends \
    usbip \
    python3 \
    python3-pip && \
    rm -rf /var/lib/apt/lists/*

# Copy the requirements.txt file
COPY requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip3 install --trusted-host pypi.python.org -r /app/requirements.txt

# Copy the app files
COPY . /app

# Set the working directory
WORKDIR /app

# Expose the Flask app port
EXPOSE 5000

# Start the Flask app
CMD ["python3", "main.py"]

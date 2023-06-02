#!/bin/bash

# Update the system
sudo apt update
sudo apt upgrade -y

# Install Java Development Kit (JDK)
sudo apt install openjdk-8-jdk -y

# Install Elasticsearch
wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | sudo apt-key add -
echo "deb https://artifacts.elastic.co/packages/7.x/apt stable main" | sudo tee /etc/apt/sources.list.d/elastic-7.x.list
sudo apt update
sudo apt install elasticsearch -y

# Configure Elasticsearch
sudo sed -i 's/#cluster.name: my-application/cluster.name: my-cluster/' /etc/elasticsearch/elasticsearch.yml
sudo sed -i 's/#network.host: 192.168.0.1/network.host: localhost/' /etc/elasticsearch/elasticsearch.yml

# Start and enable Elasticsearch service
sudo systemctl start elasticsearch
sudo systemctl enable elasticsearch

# Install Logstash
sudo apt install logstash -y

# Configure Logstash
sudo tee /etc/logstash/conf.d/logstash.conf > /dev/null <<EOT
input {
    # Configure your input source(s) here
}

filter {
    # Configure your filters here
}

output {
    elasticsearch {
        hosts => ["localhost:9200"]
        index => "your-index-name-%{+YYYY.MM.dd}"
    }
}
EOT

# Start and enable Logstash service
sudo systemctl start logstash
sudo systemctl enable logstash

# Install Kibana
sudo apt install kibana -y

# Configure Kibana
sudo sed -i 's/#server.host: "localhost"/server.host: "0.0.0.0"/' /etc/kibana/kibana.yml
sudo sed -i 's/#elasticsearch.hosts:/elasticsearch.hosts:/' /etc/kibana/kibana.yml
sudo sed -i 's/#\s*elasticsearch.hosts:\s*["http:\/\/localhost:9200"]/elasticsearch.hosts: ["http:\/\/localhost:9200"]/g' /etc/kibana/kibana.yml

# Start and enable Kibana service
sudo systemctl start kibana
sudo systemctl enable kibana

# Firewall configuration (optional)
sudo ufw allow 5601   # Kibana default port
sudo ufw allow 9200   # Elasticsearch HTTP port
sudo ufw allow 5044   # Logstash Beats input port (if used)
sudo ufw reload

# Print instructions to access Kibana
echo "ELK stack installation completed."
echo "Access Kibana by opening a web browser and navigating to: http://localhost:5601"

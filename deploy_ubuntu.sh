#!/bin/bash
# MIT-Loop Ubuntu Server Setup Script

echo "Updating System..."
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv git nginx -y

echo "Setting up Virtual Environment..."
cd /home/ubuntu/mit-loop-live # Adjust path as needed
python3 -m venv venv
source venv/bin/activate

echo "Installing Dependencies..."
pip install -r requirements.txt

echo "Creating Systemd Service..."
# This ensures your bot runs forever in the background and restarts if the server reboots.
sudo bash -c 'cat > /etc/systemd/system/mitloop.service <<EOF
[Unit]
Description=MIT-Loop Live Trading Engine
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/mit-loop-live
ExecStart=/home/ubuntu/mit-loop-live/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF'

sudo systemctl daemon-reload
sudo systemctl enable mitloop
sudo systemctl start mitloop

echo " System Deployed! Engine is running."
echo "Access your Web UI at http://YOUR_UBUNTU_IP_ADDRESS:8000"

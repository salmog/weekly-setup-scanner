4. Ubuntu A to Z Deployment Guide
When you spin up a fresh Ubuntu server (e.g., on AWS, DigitalOcean, or Hetzner), here is the exact sequence of terminal commands to go from a blank OS to running your portfolio engine.

Step 1: System Update & Install Dependencies (Git & Docker)

Bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y git curl apt-transport-https ca-certificates software-properties-common

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo apt-get install -y docker-compose-plugin

# Give your user permission to run Docker without 'sudo'
sudo usermod -aG docker $USER
newgrp docker
Step 2: Clone Your Repository

Bash
# You will need to generate an SSH key or use a PAT (Personal Access Token) to clone private repos
git clone https://github.com/your-username/mit-loop.git
cd mit-loop
Step 3: Provide Historical Data
Since we .gitignore'd the heavy CSVs, you will need to download or transfer your historical stock data into the Ubuntu server's /backend/historical_data folder before running the engine.

Bash
# Example: Use SCP from your local mac to send the data to the server
# Run this on your MAC, not the Ubuntu server:
# scp -r /Users/salmog/test/mit-loop/backend/historical_data ubuntu@<server-ip>:/home/ubuntu/mit-loop/backend/
Step 4: Build and Launch the System

Bash
# Build the images and start the database/backend containers in the background
docker compose up -d --build
Step 5: Run the Quantitative Pipeline

Bash
# 1. Generate the Trades (Will take a while on thousands of tickers)
docker compose exec backend python run_portfolio.py

# 2. Run the Risk/Compounding Simulator
docker compose exec backend python simulate_finite_portfolio.py

# 3. (Optional) Run the Machine Learning Optimizer
docker compose exec backend env PYTHONPATH=/code python -m app.research.sweep_production
Let me know once you have this committed to Git! We can then push forward with dynamically re-injecting the ML probability filter back into the simulate_finite_portfolio.py script to see if we can push that Sharpe ratio past 2.0.

Perfect, Version 2.0 is fully secured in the cloud. If this server ever crashes, or if you want to deploy this exact engine onto a brand-new Mac or Ubuntu machine, the recovery process takes less than 2 minutes.

Because you pushed it to GitHub, you no longer need to write files from scratch. You just pull it down and turn it on.

Here is the exact step-by-step to recreate the engine on a new machine:

1. Clone the Repository
Open the terminal on the new Mac/Ubuntu and download the code directly from your GitHub:

Bash
git clone git@github.com:salmog/weekly-setup-scanner.git
cd weekly-setup-scanner
2. Create the Virtual Environment
Isolate the Python packages so they don't interfere with the new computer's system:

Bash
python3 -m venv venv
source venv/bin/activate
3. Install the Engine Dependencies
Install the required quantitative libraries:

Bash
pip install fastapi uvicorn alpaca-py pandas numpy python-dotenv apscheduler jinja2
4. Recreate the API Keys (.env)
Because Git automatically (and safely) hides .env files so hackers can't steal your broker keys, you must recreate this file on the new machine.
Create a new .env file and paste your Alpaca keys inside:

Bash
nano .env
(Paste your ALPACA_API_KEY_S1, ALPACA_SECRET_KEY_S1, etc., and save).

5. Update the Hardcoded Data Path
In your current main.py code, the engine looks for CSV files in a very specific folder: /home/shay/autotrade_dev/fetch_candles_ibkr/historical_data/.
If your new Mac has a different username or folder structure, you will simply open main.py and change the HISTORICAL_DATA_DIR variable at the top to point to wherever your CSV files live on the new computer.

6. Ignite the Engine
Run the server:

Bash
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > uvicorn.log 2>&1 &
You can then open http://localhost:8000 (or the machine's IP address) in your browser, and the V2.0 dashboard will instantly appear, fully operational!

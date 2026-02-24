# 🛡️ Monad Node Watchdog

A lightweight, self-hosted, all-in-one monitoring tool for Monad Node Operators.

[Monad Watchdog Status](https://raw.githubusercontent.com/bozdemir52/monad-node-watchdog/main/status_screenshot_example.png) *(Note: You can upload your awesome Telegram screenshot to your repo and link it here!)*

📖 Overview
As a node operator, relying solely on third-party explorers for monitoring is risky. **Monad Node Watchdog** is a Python script designed to run locally alongside your node. It communicates directly with the RPC endpoint, monitors system logs, checks hardware resources, and sends instant **Telegram Alerts** if critical issues are detected.

## ✨ Features

* **Real-time Blockchain Monitoring:** Checks block height and sync status continuously.
* **🖥️ Server Health (Hardware) Tracking:** Monitors CPU, RAM, and Disk usage in real-time. Sends alerts if usage exceeds safe thresholds.
* **🥷 Validator Log Reader:** Monitors `monad-bft` journal logs in the background. Detects missed blocks and timeouts immediately!
* **🚀 TPS Tracking & Hype Alerts:** Monitors current Transactions Per Second (TPS) in real-time and triggers automatic hype alerts when network activity spikes (e.g., TPS > 500).
* **⏰ Automated & On-Demand Reports:** Receive automatic status summaries, or fetch instant data anytime using the `/status` command in Telegram.
* **🛑 Stall Detection:** Alerts you immediately if block production halts or the node gets stuck for more than 3 minutes.
* **Privacy Focused:** No external data leaks; connects only to your local RPC and the official Telegram API.

## 🚀 Installation & Usage

### 1. Clone the Repository
Download the script to your server:
```bash
git clone [https://github.com/bozdemir52/monad-node-watchdog.git](https://github.com/bozdemir52/monad-node-watchdog.git)
cd monad-node-watchdog
2. Install Requirements
Install the necessary Python libraries (requests for API calls, psutil for hardware monitoring):

Bash
pip3 install requests psutil
3. Configuration
Rename the example config file and enter your details:

Bash
mv config.py.example config.py
nano config.py
Settings to edit in your config / script:

TELEGRAM_BOT_TOKEN: Get this from @BotFather.

TELEGRAM_CHAT_ID: Get this from @userinfobot.

NODE_RPC_URL: Usually http://localhost:8080

VALIDATOR_MONIKER: Your node's name for the dashboard.

ALERT_CPU_THRESHOLD, ALERT_RAM_THRESHOLD, ALERT_DISK_THRESHOLD: Customize your hardware alert limits (default is 90%).

🛠️ Running in Background (Persistent)
To keep the bot running even after you disconnect from the server, use screen.

Create a New Session:

Bash
screen -S watchdog
Start the Script:

Bash
python3 monitor.py
(You should see: "🚀 [INFO] Monad Ultimate Validator Watchdog started...")

Detach (Leave it running):
To exit the screen without stopping the bot:
Press Ctrl + A, then release and press D.
(You will be returned to your main terminal, but the bot continues running in the background.)

🔄 Management
View Logs (Re-attach):
To check if the bot is still running or to see logs:

Bash
screen -r watchdog
Stop the Bot:

Re-attach to the screen: screen -r watchdog

Press Ctrl + C to stop the script.

Type exit to close the screen session.

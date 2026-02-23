# 🛡️ Monad Node Watchdog

**A lightweight, self-hosted monitoring tool for Monad Node Operators.**

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Monad](https://img.shields.io/badge/Network-Monad-purple)

## 📖 Overview
As a node operator, relying solely on third-party explorers for monitoring is risky. **Monad Node Watchdog** is a Python script designed to run locally alongside your node. It communicates directly with the RPC endpoint and sends instant **Telegram Alerts** if critical issues are detected.

### ✨ **Features**

* **Real-time Monitoring:** Checks block height and sync status continuously.
* **🚀 TPS Tracking & Hype Alerts:** Monitors current Transactions Per Second (TPS) in real-time and triggers automatic hype alerts when network activity spikes (e.g., TPS > 500).
* **⏰ Automated & On-Demand Reports:** Receive automatic status summaries every hour, or fetch instant data anytime using the `/status` command.
* **Stall Detection:** Alerts you immediately if block production halts or the node gets stuck for more than 3 minutes.
* **Sync Status:** Warns if the node falls behind the network.
* **Lightweight:** Uses minimal system resources (ideal for bare-metal or VPS).
* **Privacy Focused:** No external data leaks; connects only to your local RPC and the official Telegram API.

---

# 🚀 Installation & Usage

### 1. Clone the Repository
Download the script to your server:
```bash
git clone [https://github.com/bozdemir52/monad-node-watchdog.git](https://github.com/bozdemir52/monad-node-watchdog.git)
cd monad-node-watchdog
```

2. Install Requirements
Install the necessary Python library:

```Bash

pip3 install requests
```
3. Configuration
Rename the example config file and enter your details:

```Bash

mv config.py.example config.py
nano config.py
```
Settings to edit in config.py:

TELEGRAM_BOT_TOKEN: Get this from @BotFather.

TELEGRAM_CHAT_ID: Get this from @userinfobot.

NODE_RPC_URL: Usually http://localhost:8080 (for EVM) or http://localhost:26657 (for CometBFT).

🛠️ Running in Background (Persistent)
To keep the bot running even after you disconnect from the server, use screen.

1. Create a New Session
```Bash

screen -S watchdog
```
2. Start the Script
```Bash

python3 monitor.py
```
You should see: "🛡️ Monad Node Watchdog Started..."

3. Detach (Leave it running)
To exit the screen without stopping the bot:

Press Ctrl + A, then release and press D.

(You will be returned to your main terminal, but the bot continues running in the background.)

🔄 Management
View Logs (Re-attach)
To check if the bot is still running or to see logs:

```Bash

screen -r watchdog
```
Stop the Bot
Re-attach to the screen: screen -r watchdog

Press Ctrl + C to stop the script.

Type exit to close the screen session.

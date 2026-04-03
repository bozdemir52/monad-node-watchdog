# -*- coding: utf-8 -*-
import requests
import time
import datetime
import psutil
import subprocess
import threading
import re

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"
DISCORD_WEBHOOK_URL = ""  # Paste your Discord Webhook URL here (Leave empty if not using)
WATCHDOG_SERVER_IP = ""   # IP and port of your external Heartbeat server (Leave empty if not using)
NODE_RPC_URL = "http://localhost:8080" # BURAYI KONTROL ET (8080 veya 8545 olabilir)
VALIDATOR_MONIKER = "YOUR_VAL_MONIKER_NAME"

# --- API TRACKING ---
VALIDATOR_ADDRESS = "YOUR_WALLET_ADDRESS"
VALIDATOR_API_URL = f"https://monad-api.monadvision.com/testnet/api/validator/detail?validatorAddress={VALIDATOR_ADDRESS}"
NETWORK_API_URL = "https://monad-api.monadvision.com/testnet/api/overview"

# BROWSER SPOOFING (Anti-Bot Bypass)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://monadvision.com",
    "Referer": "https://monadvision.com/"
}

# Alert Thresholds
ALERT_CPU_THRESHOLD = 90
ALERT_DISK_THRESHOLD = 90
ALERT_RAM_THRESHOLD = 90
ALERT_TIMEOUT_THRESHOLD = 5
TPS_THRESHOLD = 500
# ------------------------

CHECK_INTERVAL = 2  
AUTO_REPORT_INTERVAL = 1 * 60 * 60  
HYPE_COOLDOWN = 120 

start_time = time.time()
last_update_id = None
is_spiking = False
missed_block_counter = 0  

# Disk I/O tracking
last_io_counters = None
last_io_time = 0

# Session Tracking
initial_rewards = None

def get_uptime():
    seconds = time.time() - start_time
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    return f"{int(d)}d {int(h)}h {int(m)}m"

def format_bytes(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0

def telegram_api(method, data=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        if data:
            response = requests.post(url, data=data, timeout=5)
        else:
            response = requests.get(url, timeout=5)
        return response.json()
    except Exception:
        return None

def send_message(chat_id, text):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    telegram_api("sendMessage", data)

def send_alert(text):
    send_message(TELEGRAM_CHAT_ID, text)

# --- EXPLORER API DATA ---
def get_validator_api_details():
    try:
        response = requests.get(VALIDATOR_API_URL, headers=HEADERS, timeout=10)
        response.raise_for_status() 
        data = response.json()
        if data.get("code") == 0 and "result" in data:
            res = data["result"]
            return {
                "stake": float(res.get("stake", 0)),
                "power": float(res.get("power", 0)),
                "rewards": float(res.get("commissionReward", 0)),
                "delegators": int(res.get("delegators", 0)),
                "apy": float(res.get("apy", 0))
            }
    except Exception as e:
        print(f"[API ERROR] Validator Fetch Failed: {e}")
    return None

def get_network_overview():
    try:
        response = requests.get(NETWORK_API_URL, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("code") == 0 and "result" in data:
            res = data["result"]
            return {
                "latest_block": int(res.get("latestBlockNumber", 0)),
                "tx_24h": int(res.get("transaction24h", 0)),
                "validators": int(res.get("totalValidators", 0)),
                "peak_tps": int(res.get("peakTPS", 0))
            }
    except Exception as e:
        print(f"[API ERROR] Network Fetch Failed: {e}")
    return None
# ---------------------------------------------

def get_eth_block_details():
    payload = {"jsonrpc": "2.0", "method": "eth_getBlockByNumber", "params": ["latest", False], "id": 1}
    try:
        response = requests.post(NODE_RPC_URL, json=payload, timeout=5)
        response.raise_for_status()
        data = response.json()
        if "result" in data and data["result"]:
            height = int(data["result"]["number"], 16)
            tx_count = len(data["result"]["transactions"])
            return height, tx_count
        return None, 0
    except Exception:
        return None, 0

def get_system_health():
    global last_io_counters, last_io_time
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory().percent
    disk_usage = psutil.disk_usage('/')
    disk_percent = disk_usage.percent
    disk_str = f"{format_bytes(disk_usage.used)} / {format_bytes(disk_usage.total)} ({disk_percent}%)"
    
    io_counters = psutil.disk_io_counters()
    current_time = time.time()
    read_speed_mb = 0.0
    write_speed_mb = 0.

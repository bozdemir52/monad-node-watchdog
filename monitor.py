# -*- coding: utf-8 -*-
import requests
import time
import datetime
import sys
import psutil
import subprocess
import threading

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"
NODE_RPC_URL = "http://localhost:8080"
VALIDATOR_MONIKER = "VAL_MONIKER_HERE"

# Alert Thresholds
ALERT_CPU_THRESHOLD = 90
ALERT_DISK_THRESHOLD = 90
ALERT_RAM_THRESHOLD = 90
ALERT_TIMEOUT_THRESHOLD = 5  # Consecutive timeouts/missed blocks required to trigger an alert
TPS_THRESHOLD = 500
# ------------------------

CHECK_INTERVAL = 2  
AUTO_REPORT_INTERVAL = 1 * 60 * 60  

start_time = time.time()
last_update_id = None
is_spiking = False
missed_block_counter = 0  # Counter for the ninja log reader

def get_uptime():
    seconds = time.time() - start_time
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    return f"{int(d)}d {int(h)}h {int(m)}m"

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
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    return cpu, ram, disk

def create_status_message(height, tps, cpu, ram, disk):
    if height is None:
        return "🚨 *ERROR:* Cannot reach the Node!"
    
    uptime = get_uptime()
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Determine validator status emoji based on the timeout counter
    val_status = "✅ `Active / Signing`"
    if missed_block_counter > 0:
        val_status = f"⚠️ `Missing Blocks! ({missed_block_counter})`"
    
    msg = (
        f"🛡️ *{VALIDATOR_MONIKER} | MONAD WATCHDOG*\n"
        f"📅 `{now}`\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "**⛓️ Blockchain & Validator**\n"
        f"🧱 *Latest Block:* `{height}`\n"
        f"⚡ *Current TPS:* `{tps}`\n"
        f"✍️ *Validator Status:* {val_status}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "**🖥️ Server Health (Hardware)**\n"
        f"🧠 *CPU Usage:* `{cpu}%`\n"
        f"💾 *RAM Usage:* `{ram}%`\n"
        f"💽 *Disk Usage:* `{disk}%`\n"
        f"⏳ *Bot Uptime:* `{uptime}`\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 _Type /status to update._"
    )
    return msg

# --- NINJA LOG READER (BACKGROUND PROCESS) ---
def monitor_logs():
    global missed_block_counter
    print("🥷 [INFO] Ninja Log Reader started. Monitoring 'monad-bft' logs...")
    
    process = subprocess.Popen(['journalctl', '-u', 'monad-bft', '-f', '-n', '0'], 
                               stdout=subprocess.PIPE, 
                               stderr=subprocess.STDOUT, 
                               text=True)
    
    for line in process.stdout:
        line_lower = line.lower()
        
        # Catch only consensus or validator-related errors. Ignore trivial P2P or keepalive timeouts.
        if "consensus timeout" in line_lower or "failed to propose" in line_lower or "missed block" in line_lower:
            missed_block_counter += 1
            print(f"⚠️ [WARN] Consensus issue detected! Streak: {missed_block_counter}")
            
        # Detect successful vote transmission or block creation to reset the counter.
        elif "sending vote" in line_lower or "committed state" in line_lower:
            if missed_block_counter > 0:
                print(f"✅ [INFO] Validator recovered (Vote sent). Resetting timeout counter.")
            missed_block_counter = 0
# --------------------------------------------

def check_updates():
    global last_update_id
    params = {"timeout": 0}
    if last_update_id:
        params["offset"] = last_update_id + 1
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        if not data.get("ok"): return

        for result in data.get("result", []):
            last_update_id = result["update_id"]
            if "message" in result and "text" in result["message"]:
                text = result["message"]["text"]
                chat_id = result["message"]["chat"]["id"]
                
                if str(chat_id) == str(TELEGRAM_CHAT_ID):
                    if text == "/start":
                        send_message(chat_id, "👋 Hello! I am your Ultimate Validator Watchdog.\nType */status* for detailed metrics.")
                    elif text == "/status":
                        send_message(chat_id, "🔄 Fetching dashboard...")
                        height, tps = get_eth_block_details()
                        cpu, ram, disk = get_system_health()
                        msg = create_status_message(height, tps, cpu, ram, disk)
                        send_message(chat_id, msg)
    except Exception:
        pass

def main():
    global is_spiking, missed_block_counter
    print("🚀 [INFO] Monad Ultimate Validator Watchdog started...")
    send_message(TELEGRAM_CHAT_ID, "🚀 *Watchdog Started!*\nMonitoring Hardware, Validator Logs, and TPS. Type `/status`.")
    
    # Start the log reader in the background as a separate thread
    log_thread = threading.Thread(target=monitor_logs, daemon=True)
    log_thread.start()
    
    last_height = 0
    stuck_counter = 0
    last_report_time = time.time()
    last_hardware_alert_time = 0 
    
    while True:
        check_updates()
        current_height, current_tps = get_eth_block_details()
        cpu, ram, disk = get_system_health()
        
        # --- ALERTS: TIMEOUT / MISSED BLOCK ---
        if missed_block_counter >= ALERT_TIMEOUT_THRESHOLD:
            send_message(TELEGRAM_CHAT_ID, f"🚨 **VALIDATOR ALERT** 🚨\n\nYour validator missed `{missed_block_counter}` consecutive blocks (Timeout)!\nCheck your node status immediately.")
            missed_block_counter = 0  # Reset to prevent spamming
            time.sleep(10) # Wait for 10 seconds

        # --- ALERTS: HARDWARE ---
        if time.time() - last_hardware_alert_time > 300: 
            alert_msg = ""
            if cpu > ALERT_CPU_THRESHOLD: alert_msg += f"⚠️ *HIGH CPU ALERT:* `{cpu}%`\n"
            if ram > ALERT_RAM_THRESHOLD: alert_msg += f"⚠️ *HIGH RAM ALERT:* `{ram}%`\n"
            if disk > ALERT_DISK_THRESHOLD: alert_msg += f"🆘 *CRITICAL DISK ALERT:* `{disk}%`\n"
                
            if alert_msg:
                send_message(TELEGRAM_CHAT_ID, f"🚨 **SYSTEM RESOURCE WARNING** 🚨\n\n{alert_msg}")
                last_hardware_alert_time = time.time()

        if current_height is not None:
            if current_height != last_height:
                print(f"🧱 Block: {current_height} | TPS: {current_tps} | CPU: {cpu}% | Timeouts: {missed_block_counter}")
                
                # HYPE ALERT
                if current_tps > TPS_THRESHOLD and not is_spiking:
                    is_spiking = True
                    send_message(TELEGRAM_CHAT_ID, f"🚀 *MONAD HYPE ALERT!*\n\nNetwork is under heavy load! 🔥\nCurrent TPS: *{current_tps}*\nBlock: `{current_height}`")
                elif current_tps <= TPS_THRESHOLD:
                    is_spiking = False
                    
                stuck_counter = 0
            else:
                stuck_counter += 1

            # STUCK ALERT
            if stuck_counter >= 90: 
                send_message(TELEGRAM_CHAT_ID, f"🛑 *ALERT: Node STUCK!*\nBlock: `{current_height}`\nNo new blocks for 3 minutes. Check your node!")
                stuck_counter = 0 

            # AUTOMATIC REPORT
            if time.time() - last_report_time > AUTO_REPORT_INTERVAL:
                msg = create_status_message(current_height, current_tps, cpu, ram, disk)
                send_message(TELEGRAM_CHAT_ID, "⏰ *AUTOMATIC REPORT*\n\n" + msg)
                last_report_time = time.time()
            
            last_height = current_height
            
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()

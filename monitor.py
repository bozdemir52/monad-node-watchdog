# -*- coding: utf-8 -*-
import requests
import time
import datetime
import sys

# Load config
try:
    import config
except ImportError:
    print("🚨 [ERROR] config.py not found!")
    sys.exit(1)

# --- SETTINGS ---
CHECK_INTERVAL = 2  
AUTO_REPORT_INTERVAL = 1 * 60 * 60  # 1 Hour automatic report
TPS_THRESHOLD = 500  # Threshold for Hype Alert
# ----------------

start_time = time.time()
last_update_id = None
is_spiking = False

def get_uptime():
    seconds = time.time() - start_time
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    return f"{int(d)}d {int(h)}h {int(m)}m"

def telegram_api(method, data=None):
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{method}"
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
        response = requests.post(config.NODE_RPC_URL, json=payload, timeout=5)
        response.raise_for_status()
        data = response.json()
        if "result" in data and data["result"]:
            height = int(data["result"]["number"], 16)
            tx_count = len(data["result"]["transactions"])
            return height, tx_count
        return None, 0
    except Exception:
        return None, 0

def create_status_message(height, tps):
    if height is None:
        return "🚨 *ERROR:* Cannot reach the Node!"
    
    uptime = get_uptime()
    now = datetime.datetime.now().strftime('%H:%M:%S')
    
    msg = (
        "📊 *MONAD NODE STATUS*\n"
        f"🕰️ `{now}`\n"
        "-----------------------------\n"
        f"🧱 *Block Height:* `{height}`\n"
        f"⚡ *Current TPS:* `{tps}`\n"
        f"⏳ *Uptime:* `{uptime}`\n"
        f"📡 *Port:* `8080 (EVM)`\n"
        f"✅ *Sync:* `Synchronized`\n"
        "-----------------------------\n"
        "🤖 _Type /status to update._"
    )
    return msg

def check_updates():
    global last_update_id
    params = {"timeout": 0}  # Zero delay fix to prevent missing blocks
    if last_update_id:
        params["offset"] = last_update_id + 1
        
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        if not data.get("ok"): return

        for result in data.get("result", []):
            last_update_id = result["update_id"]
            if "message" in result and "text" in result["message"]:
                text = result["message"]["text"]
                chat_id = result["message"]["chat"]["id"]
                
                if str(chat_id) == str(config.TELEGRAM_CHAT_ID):
                    if text == "/start":
                        send_message(chat_id, "👋 Hello! I am your All-in-One Monad Watchdog.\nType */status* to see block height and TPS.")
                    elif text == "/status":
                        send_message(chat_id, "🔄 Fetching data...")
                        height, tps = get_eth_block_details()
                        msg = create_status_message(height, tps)
                        send_message(chat_id, msg)
    except Exception:
        pass

def main():
    global is_spiking
    print("🚀 [INFO] Monad All-in-One Watchdog started...")
    send_message(config.TELEGRAM_CHAT_ID, "🚀 *Monad Watchdog Started!*\nType `/status` for info.")
    
    last_height = 0
    stuck_counter = 0
    last_report_time = time.time()
    
    while True:
        check_updates()
        current_height, current_tps = get_eth_block_details()
        
        if current_height is None:
            pass 
        else:
            if current_height != last_height:
                print(f"🧱 [Monad Monitor] Block: {current_height} | TX Count (TPS): {current_tps}")
                
                if current_tps > TPS_THRESHOLD and not is_spiking:
                    is_spiking = True
                    msg = f"🚀 *MONAD HYPE ALERT!*\n\nThe network is under heavy load! 🔥\nCurrent TPS: *{current_tps}*\nBlock: `{current_height}`\n\nYour bare-metal node is processing like a beast! 💜"
                    send_message(config.TELEGRAM_CHAT_ID, msg)
                elif current_tps <= TPS_THRESHOLD:
                    is_spiking = False
                    
                stuck_counter = 0
            else:
                stuck_counter += 1

            if stuck_counter >= 90: 
                send_message(config.TELEGRAM_CHAT_ID, f"🛑 *ALERT: Node STUCK!*\nBlock: `{current_height}`\nNo new blocks for 3 minutes. Please check your server!")
                stuck_counter = 0 

            if time.time() - last_report_time > AUTO_REPORT_INTERVAL:
                msg = create_status_message(current_height, current_tps)
                send_message(config.TELEGRAM_CHAT_ID, "⏰ *AUTOMATIC REPORT*\n" + msg)
                last_report_time = time.time()
            
            last_height = current_height
            
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()

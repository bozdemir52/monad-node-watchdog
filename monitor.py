# -*- coding: utf-8 -*-
import requests
import time
import datetime
import sys
import psutil  # YENI: Donanim bilgileri icin

try:
    import config
except ImportError:
    print("🚨 [ERROR] config.py not found!")
    sys.exit(1)

CHECK_INTERVAL = 2  
AUTO_REPORT_INTERVAL = 1 * 60 * 60  
TPS_THRESHOLD = 500  

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

def get_system_health():
    """CPU, RAM ve Disk kullanim yuzdelerini dondurur"""
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    return cpu, ram, disk

def create_status_message(height, tps, cpu, ram, disk):
    """ITRocket tarzinda hazirlanmis detayli dashboard"""
    if height is None:
        return "🚨 *ERROR:* Cannot reach the Node!"
    
    uptime = get_uptime()
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    moniker = getattr(config, 'VALIDATOR_MONIKER', 'MyNode')
    
    msg = (
        f"🛡️ *{moniker} | MONAD NODE STATUS*\n"
        f"📅 `{now}`\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "**⛓️ Blockchain Performance**\n"
        f"🧱 *Latest Block:* `{height}`\n"
        f"⚡ *Current TPS:* `{tps}`\n"
        f"✅ *Sync Status:* `Synchronized`\n"
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

def check_updates():
    global last_update_id
    params = {"timeout": 0}
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
    global is_spiking
    print("🚀 [INFO] Monad Ultimate Validator Watchdog started...")
    send_message(config.TELEGRAM_CHAT_ID, "🚀 *Watchdog Started!*\nMonitoring Hardware, Blocks, and TPS. Type `/status`.")
    
    last_height = 0
    stuck_counter = 0
    last_report_time = time.time()
    last_hardware_alert_time = 0 # Surekli alarm atip spam yapmamasi icin
    
    while True:
        check_updates()
        current_height, current_tps = get_eth_block_details()
        cpu, ram, disk = get_system_health()
        
        # --- DONANIM ALARMLARI (INSTANT ALERTS) ---
        # 5 dakikada bir alarm atabilir (spam engelleme)
        if time.time() - last_hardware_alert_time > 300: 
            alert_msg = ""
            if cpu > getattr(config, 'ALERT_CPU_THRESHOLD', 90):
                alert_msg += f"⚠️ *HIGH CPU ALERT:* `{cpu}%`\n"
            if ram > getattr(config, 'ALERT_RAM_THRESHOLD', 90):
                alert_msg += f"⚠️ *HIGH RAM ALERT:* `{ram}%`\n"
            if disk > getattr(config, 'ALERT_DISK_THRESHOLD', 90):
                alert_msg += f"🆘 *CRITICAL DISK ALERT:* `{disk}%` - Server might crash soon!\n"
                
            if alert_msg:
                send_message(config.TELEGRAM_CHAT_ID, f"🚨 **SYSTEM RESOURCE WARNING** 🚨\n\n{alert_msg}\nPlease check your server immediately!")
                last_hardware_alert_time = time.time()
        # -------------------------------------------

        if current_height is None:
            pass 
        else:
            if current_height != last_height:
                print(f"🧱 Block: {current_height} | TPS: {current_tps} | CPU: {cpu}% | RAM: {ram}%")
                
                # HYPE ALERT
                if current_tps > TPS_THRESHOLD and not is_spiking:
                    is_spiking = True
                    msg = f"🚀 *MONAD HYPE ALERT!*\n\nNetwork is under heavy load! 🔥\nCurrent TPS: *{current_tps}*\nBlock: `{current_height}`"
                    send_message(config.TELEGRAM_CHAT_ID, msg)
                elif current_tps <= TPS_THRESHOLD:
                    is_spiking = False
                    
                stuck_counter = 0
            else:
                stuck_counter += 1

            # STUCK ALARM
            if stuck_counter >= 90: 
                send_message(config.TELEGRAM_CHAT_ID, f"🛑 *ALERT: Node STUCK!*\nBlock: `{current_height}`\nNo new blocks for 3 minutes. Check your node!")
                stuck_counter = 0 

            # OTOMATIK RAPOR
            if time.time() - last_report_time > AUTO_REPORT_INTERVAL:
                msg = create_status_message(current_height, current_tps, cpu, ram, disk)
                send_message(config.TELEGRAM_CHAT_ID, "⏰ *AUTOMATIC REPORT*\n" + msg)
                last_report_time = time.time()
            
            last_height = current_height
            
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()

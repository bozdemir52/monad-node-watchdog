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
WATCHDOG_SERVER_IP = ""   # IP and port of your external Heartbeat server (e.g., "http://192.168.1.100:5000") (Leave empty if not using)
NODE_RPC_URL = "http://localhost:8080" 
VALIDATOR_MONIKER = "YOUR_VAL_MONIKER_NAME"

# --- HUGINN API TRACKING ---
VALIDATOR_ADDRESS = "YOUR_SECP_ADDRESS"
HUGINN_BASE_URL = "https://validator-api-testnet.huginn.tech/monad-api"

# Alert Thresholds
ALERT_CPU_THRESHOLD = 90
ALERT_DISK_THRESHOLD = 90
ALERT_RAM_THRESHOLD = 90
ALERT_TIMEOUT_THRESHOLD = 5
# ------------------------

CHECK_INTERVAL = 2  
AUTO_REPORT_INTERVAL = 1 * 60 * 60  

start_time = time.time()
last_update_id = None
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

# --- HUGINN EXPLORER API DATA ---
def get_validator_api_details():
    try:
        # 1. Adım: Cüzdan adresinden Validator ID ve Uptime bilgisini çek
        uptime_url = f"{HUGINN_BASE_URL}/validator/uptime/{VALIDATOR_ADDRESS}"
        uptime_response = requests.get(uptime_url, timeout=10)
        uptime_data = uptime_response.json()

        # Uptime datası bazen 'uptime' objesi içinde dönüyor
        val_info = uptime_data.get("uptime", uptime_data)
        val_id = val_info.get("validator_id")

        # Uptime hesaplama
        total_events = val_info.get("total_events", 0)
        finalized = val_info.get("finalized_count", 0)
        uptime_pct = (finalized / total_events * 100) if total_events > 0 else 0.0

        stake = 0.0
        rewards = 0.0

        # 2. Adım: Bulunan ID ile Stake ve Ödül verilerini çek
        if val_id:
            stake_url = f"{HUGINN_BASE_URL}/staking/validator/{val_id}"
            stake_response = requests.get(stake_url, timeout=10)
            if stake_response.status_code == 200:
                stake_data = stake_response.json()
                
                # YENİ JSON YAPISINA GÖRE DÜZELTİLDİ: "validator" objesinin içine giriyoruz
                if stake_data.get("success") and "validator" in stake_data:
                    v_data = stake_data["validator"]
                    stake = float(v_data.get("stake", 0))
                    rewards = float(v_data.get("unclaimed_rewards", 0))

        return {
            "val_id": val_id,
            "stake": stake,
            "rewards": rewards,
            "uptime_pct": uptime_pct
        }

    except Exception as e:
        print(f"[API ERROR] Huginn Fetch Failed: {e}")
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
    write_speed_mb = 0.0
    
    if last_io_counters and (current_time - last_io_time) > 0:
        time_diff = current_time - last_io_time
        read_speed_mb = (io_counters.read_bytes - last_io_counters.read_bytes) / time_diff / (1024 * 1024)
        write_speed_mb = (io_counters.write_bytes - last_io_counters.write_bytes) / time_diff / (1024 * 1024)
        
    last_io_counters = io_counters
    last_io_time = current_time
    disk_io_str = f"{read_speed_mb:.2f} MB/s Read | {write_speed_mb:.2f} MB/s Write"
    
    return cpu, ram, disk_percent, disk_str, disk_io_str

def get_monad_status_details():
    details = {"triedb_percent": None, "triedb_str": "N/A", "sync_status": "Unknown", "epoch": "N/A", "round": "N/A"}
    try:
        result = subprocess.run(['monad-status'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        lines = result.stdout.split('\n')
        in_consensus = False
        capacity_str = ""
        used_amount_str = ""
        
        for line in lines:
            if line.startswith('consensus:'): in_consensus = True
            elif line.startswith('statesync:') or line.startswith('rpc:'): in_consensus = False
            
            if in_consensus:
                if 'status:' in line: details["sync_status"] = line.split('status:')[1].strip()
                elif 'epoch:' in line: details["epoch"] = line.split('epoch:')[1].strip()
                elif 'round:' in line: details["round"] = line.split('round:')[1].strip()
            
            if 'capacity:' in line: capacity_str = line.split('capacity:')[1].strip()
            if 'used:' in line and '%' in line:
                match = re.search(r'used:\s*(.*?)\s*\(([\d\.]+)%\)', line)
                if match:
                    used_amount_str = match.group(1).strip()
                    details["triedb_percent"] = float(match.group(2))
        
        if capacity_str and used_amount_str and details["triedb_percent"] is not None:
            details["triedb_str"] = f"{used_amount_str} / {capacity_str} ({details['triedb_percent']}%)"
        elif details["triedb_percent"] is not None:
            details["triedb_str"] = f"{details['triedb_percent']}%"
        return details
    except Exception:
        return details

def create_status_message(local_height, tps, cpu, ram, disk_str, disk_io_str, monad_details, val_data):
    if local_height is None:
        return "🚨 *ERROR:* Cannot reach the local Node RPC!"
    
    uptime = get_uptime()
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    val_status = "✅ `Active / Signing`"
    if missed_block_counter > 0:
        val_status = f"⚠️ `Missing Blocks! ({missed_block_counter})`"
        
    triedb_str = monad_details.get("triedb_str", "N/A")
    sync_status = monad_details.get("sync_status", "Unknown")
    epoch = monad_details.get("epoch", "N/A")
    rnd = monad_details.get("round", "N/A")
    
    sync_emoji = "🟢" if sync_status == "in-sync" else "🟡"

    # Validator Data
    if val_data and val_data.get('val_id') is not None:
        stake = val_data['stake']
        rewards = val_data['rewards']
        uptime_pct = val_data['uptime_pct']
        
        session_earned = rewards - initial_rewards if initial_rewards is not None else 0.0
        
        val_section = (
            "**🏆 Huginn Validator Stats**\n"
            f"🆔 *Val ID:* `#{val_data['val_id']}` | 🟢 *Uptime:* `{uptime_pct:.2f}%`\n"
            f"💰 *Rewards:* `{rewards:,.2f} MON`\n"
            f"📈 *Session Earned:* `+{session_earned:,.4f} MON`\n"
            f"💎 *Stake:* `{stake:,.2f} MON`\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
        )
    else:
        val_section = "**🏆 Validator Stats**\n⚠️ *Huginn API Verisi Bekleniyor*\n━━━━━━━━━━━━━━━━━━━━━\n"

    msg = (
        f"🛡️ *{VALIDATOR_MONIKER} | MONAD WATCHDOG*\n"
        f"📅 `{now}`\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "**⛓️ Blockchain & Node**\n"
        f"🧱 *Local Block:* `{local_height}`\n"
        f"⚡ *Current TPS:* `{tps}`\n"
        f"🔄 *Sync Status:* {sync_emoji} `{sync_status}`\n"
        f"🎯 *Epoch / Round:* `{epoch} / {rnd}`\n"
        f"✍️ *Node Status:* {val_status}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        + val_section +
        "**🖥️ Server Health**\n"
        f"🧠 *CPU:* `{cpu}%` | 💾 *RAM:* `{ram}%`\n"
        f"💽 *OS Disk:* `{disk_str}`\n"
        f"⚙️ *Disk I/O:* `{disk_io_str}`\n"
        f"🗄️ *TrieDB:* `{triedb_str}`\n"
        f"⏳ *Bot Uptime:* `{uptime}`\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 _Type /status to update._"
    )
    return msg

def monitor_logs():
    global missed_block_counter
    print("🥷 [INFO] Ninja Log Reader started. Monitoring 'monad-bft' logs...")
    process = subprocess.Popen(['journalctl', '-u', 'monad-bft', '-f', '-n', '0'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in process.stdout:
        line_lower = line.lower()
        if "consensus timeout" in line_lower or "failed to propose" in line_lower or "missed block" in line_lower:
            missed_block_counter += 1
            print(f"⚠️ [WARN] Consensus issue detected! Streak: {missed_block_counter}")
        elif "sending vote" in line_lower or "committed state" in line_lower:
            if missed_block_counter > 0:
                print(f"✅ [INFO] Validator recovered (Vote sent). Resetting timeout counter.")
            missed_block_counter = 0

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
                        send_message(chat_id, "👋 Hello! Type */status* for detailed metrics.")
                    elif text == "/status":
                        send_message(chat_id, "🔄 Fetching dashboard...")
                        local_height, tps = get_eth_block_details()
                        cpu, ram, disk_percent, disk_str, disk_io_str = get_system_health()
                        monad_details = get_monad_status_details()
                        val_data = get_validator_api_details()
                        
                        msg = create_status_message(local_height, tps, cpu, ram, disk_str, disk_io_str, monad_details, val_data)
                        send_message(chat_id, msg)
    except Exception:
        pass

def main():
    global missed_block_counter, initial_rewards
    
    print("🚀 [INFO] Monad Ultimate Validator Watchdog started...")
    # Başlangıç ödülünü kaydet
    init_data = get_validator_api_details()
    if init_data and init_data.get('rewards'):
        initial_rewards = init_data["rewards"]
        
    log_thread = threading.Thread(target=monitor_logs, daemon=True)
    log_thread.start()
    
    last_height = 0
    stuck_counter = 0
    last_report_time = time.time()
    last_hardware_alert_time = 0 
    
    while True:
        check_updates()
        current_height, current_tps = get_eth_block_details()
        cpu, ram, disk_percent, disk_str, disk_io_str = get_system_health()
        monad_details = get_monad_status_details()
        triedb_percent = monad_details.get("triedb_percent")
        
        # TIMEOUT ALERTS
        if missed_block_counter >= ALERT_TIMEOUT_THRESHOLD:
            send_alert(f"🚨 **VALIDATOR ALERT** 🚨\nMissed `{missed_block_counter}` consecutive blocks!")
            missed_block_counter = 0  
            time.sleep(10) 

        # HARDWARE ALERTS
        if time.time() - last_hardware_alert_time > 300: 
            alert_msg = ""
            if cpu > ALERT_CPU_THRESHOLD: alert_msg += f"⚠️ *HIGH CPU:* `{cpu}%`\n"
            if ram > ALERT_RAM_THRESHOLD: alert_msg += f"⚠️ *HIGH RAM:* `{ram}%`\n"
            if disk_percent > ALERT_DISK_THRESHOLD: alert_msg += f"🆘 *OS DISK:* `{disk_percent}%`\n"
            if triedb_percent is not None and triedb_percent > ALERT_DISK_THRESHOLD: 
                alert_msg += f"🗄️🆘 *TRIEDB:* `{triedb_percent}%`\n"
                
            if alert_msg:
                send_alert(f"🚨 **SYSTEM RESOURCE WARNING** 🚨\n\n{alert_msg}")
                last_hardware_alert_time = time.time()

        if current_height is not None:
            if current_height != last_height:
                stuck_counter = 0
            else:
                stuck_counter += 1

            if stuck_counter >= 90: 
                send_alert(f"🛑 *ALERT: Node STUCK!*\nBlock: `{current_height}`\nNo new blocks for 3 minutes!")
                stuck_counter = 0 

            if time.time() - last_report_time > AUTO_REPORT_INTERVAL:
                val_data = get_validator_api_details()
                msg = create_status_message(current_height, current_tps, cpu, ram, disk_str, disk_io_str, monad_details, val_data)
                send_message(TELEGRAM_CHAT_ID, "⏰ *AUTOMATIC REPORT*\n\n" + msg)
                last_report_time = time.time()
            
            last_height = current_height
            
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()

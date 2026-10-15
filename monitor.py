# -*- coding: utf-8 -*-
import requests
import time
import datetime
import psutil
import subprocess
import threading
import re

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"
DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL"
WATCHDOG_SERVER_IP = "http://YOUR_SERVER_IP:5000"
NODE_RPC_URL = "http://localhost:8080"
VALIDATOR_MONIKER = "YOUR_MONIKER"

# --- API TRACKING ---
VALIDATOR_ADDRESS = "YOUR_VALIDATOR_PUBKEY_OR_ADDRESS"
HUGINN_BASE_URL = "https://validator-api-testnet.huginn.tech/monad-api"

# --- ALERT THRESHOLDS ---
ALERT_CPU_THRESHOLD = 80
ALERT_DISK_THRESHOLD = 90
ALERT_RAM_THRESHOLD = 80
ALERT_TIMEOUT_THRESHOLD = 1
ALERT_TPS_THRESHOLD = 4500
ALERT_GAS_SEC_THRESHOLD = 300_000_000
ALERT_BASE_FEE_THRESHOLD = 150
STAKE_THRESHOLD = 11_000_000
API_LAG_THRESHOLD = 5000

# ------------------------
CHECK_INTERVAL = 2
AUTO_REPORT_INTERVAL = 1 * 60 * 60

start_time = time.time()
missed_block_counter = 0

# Disk I/O tracking
last_io_counters = None
last_io_time = 0

# Block Time Tracking variables
last_block_time_check = 0
last_block_height_for_time = 0
last_calculated_block_time_ms = 0.0

# Session Tracking
initial_rewards = None

# --- CACHE GLOBAL VARIABLES ---
cached_monad_details = {"triedb_percent": None, "triedb_str": "N/A", "sync_status": "Unknown", "epoch": "N/A", "round": "N/A"}
cached_val_api_data = None
cached_epoch_details = ("N/A", "N/A", "N/A")

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
    except Exception as e:
        print(f"⚠️ [TELEGRAM API ERROR] {e}")
        return None

def send_message(chat_id, text):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    telegram_api("sendMessage", data)

def send_alert(text):
    send_message(TELEGRAM_CHAT_ID, text)

def get_nvme_stats():
    nvme_lines = []
    try:
        ls_output = subprocess.check_output(['ls', '/dev/'], text=True)
        drives = [d for d in ls_output.split('\n') if re.match(r'^nvme\d+n\d+$', d)]
        
        for drive in drives:
            try:
                cmd = f"nvme smart-log /dev/{drive}"
                output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
                
                wear_match = re.search(r'percentage_used\s*:\s*(\d+)', output, re.IGNORECASE)
                temp_match = re.search(r'temperature\s*:\s*(\d+)', output, re.IGNORECASE)
                
                if wear_match and temp_match:
                    wear = int(wear_match.group(1))
                    temp = int(temp_match.group(1))
                    
                    emoji = "🟢" if wear < 75 else ("🟡" if wear < 100 else "🔴")
                    nvme_lines.append(f"{emoji} *NVMe {drive}:* Wear `{wear}%` | Temp `{temp}°C`")
            except Exception:
                continue
    except Exception:
        pass
        
    return "\n".join(nvme_lines) if nvme_lines else ""

def get_temperature():
    try:
        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            if not temps: return "N/A"
            for name, entries in temps.items():
                for entry in entries:
                    if entry.current:
                        return f"{entry.current}°C"
    except Exception:
        pass
    return "N/A"

def get_system_health():
    global last_io_counters, last_io_time
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent
    
    disk_info = psutil.disk_usage('/')
    disk_percent = disk_info.percent
    disk_str = f"{format_bytes(disk_info.used)} / {format_bytes(disk_info.total)} ({disk_percent}%)"
    
    current_io = psutil.disk_io_counters()
    current_time = time.time()
    disk_io_str = "0.00 MB/s Read | 0.00 MB/s Write"
    
    if last_io_counters and last_io_time:
        time_diff = current_time - last_io_time
        if time_diff > 0:
            read_speed = (current_io.read_bytes - last_io_counters.read_bytes) / time_diff / (1024 * 1024)
            write_speed = (current_io.write_bytes - last_io_counters.write_bytes) / time_diff / (1024 * 1024)
            disk_io_str = f"{read_speed:.2f} MB/s Read | {write_speed:.2f} MB/s Write"
            
    last_io_counters = current_io
    last_io_time = current_time
    
    temp_str = get_temperature()
    nvme_str = get_nvme_stats()
    
    return cpu, ram, disk_percent, disk_str, disk_io_str, temp_str, nvme_str

def get_epoch_details():
    try:
        epoch_url = f"{HUGINN_BASE_URL}/staking/epoch"
        response = requests.get(epoch_url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and "epoch" in data:
                current_epoch = data["epoch"]
                progress = data.get("progress", data.get("epoch_progress", "N/A"))
                blocks_left = data.get("blocks_remaining", data.get("time_remaining", "N/A"))
                
                if isinstance(progress, (float, int)):
                    progress_str = f"{progress * 100:.2f}" if progress < 1 else f"{progress:.2f}"
                else:
                    progress_str = str(progress)

                return current_epoch, progress_str, str(blocks_left)
    except Exception:
        pass
    return "N/A", "N/A", "N/A"

def get_validator_api_details():
    try:
        uptime_url = f"{HUGINN_BASE_URL}/validator/uptime/{VALIDATOR_ADDRESS}"
        uptime_response = requests.get(uptime_url, timeout=4)
        uptime_data = uptime_response.json()

        val_info = uptime_data.get("uptime", uptime_data)
        val_id = val_info.get("validator_id")
        api_block_height = val_info.get("last_block_height")

        total_events = val_info.get("total_events", 0)
        finalized = val_info.get("finalized_count", 0)
        timeout_count = val_info.get("timeout_count", 0)
        uptime_pct = (finalized / total_events * 100) if total_events > 0 else 0.0

        stake = 0.0
        rewards = 0.0
        is_jailed = False
        val_status = "unknown"

        if val_id:
            stake_url = f"{HUGINN_BASE_URL}/staking/validator/{val_id}"
            stake_response = requests.get(stake_url, timeout=4)
            if stake_response.status_code == 200:
                stake_data = stake_response.json()
                if stake_data.get("success") and "validator" in stake_data:
                    v_data = stake_data["validator"]
                    stake = float(v_data.get("stake", 0))
                    rewards = float(v_data.get("unclaimed_rewards", 0))
                    is_jailed = v_data.get("jailed", False)
                    val_status = v_data.get("status", "unknown")

        return {
            "val_id": val_id,
            "stake": stake,
            "rewards": rewards,
            "uptime_pct": uptime_pct,
            "timeout_count": timeout_count,
            "is_jailed": is_jailed,
            "status": val_status,
            "api_block_height": api_block_height
        }
    except Exception:
        return None

def get_eth_block_details():
    global last_block_time_check, last_block_height_for_time, last_calculated_block_time_ms
    payload = {"jsonrpc": "2.0", "method": "eth_getBlockByNumber", "params": ["latest", False], "id": 1}
    try:
        response = requests.post(NODE_RPC_URL, json=payload, timeout=2)
        response.raise_for_status()
        data = response.json()
        if "result" in data and data["result"]:
            block = data["result"]
            height = int(block["number"], 16)
            
            current_time = time.time()
            if last_block_height_for_time != 0 and height > last_block_height_for_time:
                blocks_diff = height - last_block_height_for_time
                time_diff = current_time - last_block_time_check
                last_calculated_block_time_ms = (time_diff / blocks_diff) * 1000
                last_block_time_check = current_time
                last_block_height_for_time = height
            elif last_block_height_for_time == 0:
                last_block_time_check = current_time
                last_block_height_for_time = height

            block_time_ms = last_calculated_block_time_ms

            # Dynamic block/sec calculation (fallback to Monad target ~3.33 block/s if not yet computed)
            if block_time_ms > 0:
                blocks_per_sec = 1000.0 / block_time_ms
            else:
                blocks_per_sec = 3.33

            tx_in_block = len(block["transactions"])
            estimated_tps = int(tx_in_block * blocks_per_sec)
            
            gas_used = int(block.get("gasUsed", "0x0"), 16)
            base_fee = int(block.get("baseFeePerGas", "0x0"), 16) / 10**9
            gas_per_sec = int(gas_used * blocks_per_sec)
            
            return height, estimated_tps, gas_per_sec, base_fee, block_time_ms
        return None, 0, 0, 0.0, 0.0
    except Exception:
        return None, 0, 0, 0.0, 0.0

def get_monad_status_details():
    details = {"triedb_percent": None, "triedb_str": "N/A", "sync_status": "Unknown", "epoch": "N/A", "round": "N/A"}
    try:
        result = subprocess.run(['monad-status'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3)
        lines = result.stdout.split('\n')
        in_consensus = False
        capacity_str = ""
        used_amount_str = ""
        
        for line in lines:
            if line.startswith('consensus:'): in_consensus = True
            elif line.startswith('statesync:') or line.startswith('rpc:'): in_consensus = False
            
            if in_consensus:
                if 'status:' in line: details["sync_status"] = line.split('status:')[1].strip()
                elif 'round:' in line: details["round"] = line.split('round:')[1].strip()
            
            if 'capacity:' in line: capacity_str = line.split('capacity:')[1].strip()
            if 'used:' in line and '%' in line:
                match = re.search(r'used:\s*(.*?)\s*\(([\d\.]+)\%\)', line)
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

def create_status_message():
    local_height, tps, gas_sec, base_fee, block_time_ms = get_eth_block_details()
    cpu, ram, disk_percent, disk_str, disk_io_str, temp_str, nvme_str = get_system_health()

    if local_height is None:
        return "🚨 *ERROR:* Cannot reach local Node RPC!"
    
    uptime = get_uptime()
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    api_epoch = cached_epoch_details[0]
    val_data = cached_val_api_data
    monad_details = cached_monad_details

    if val_data and val_data.get('is_jailed'):
        val_status = "🛑 `JAILED (Slashed!)`"
    elif val_data and 'stake' in val_data:
        if val_data['stake'] < STAKE_THRESHOLD:
            val_status = "💤 `Inactive / Standby`"
        elif missed_block_counter > 0:
            val_status = f"⚠️ `Missing Blocks! ({missed_block_counter})`"
        else:
            val_status = "✅ `Active / Signing`"
    else:
        val_status = "✅ `Active / Signing`"
        if missed_block_counter > 0:
            val_status = f"⚠️ `Missing Blocks! ({missed_block_counter})`"
        
    triedb_str = monad_details.get("triedb_str", "N/A")
    sync_status = monad_details.get("sync_status", "Unknown")
    rnd = monad_details.get("round", "N/A")
    sync_emoji = "🟢" if sync_status == "in-sync" else "🟡"

    if val_data and val_data.get('val_id') is not None:
        stake = val_data['stake']
        rewards = val_data['rewards']
        uptime_pct = val_data['uptime_pct']
        api_timeouts = val_data.get('timeout_count', 0)
        session_earned = rewards - initial_rewards if initial_rewards is not None else 0.0
        
        val_section = (
            "**🏆 Huginn Validator Stats**\n"
            f"🆔 *Val ID:* `#{val_data['val_id']}` | 🟢 *Uptime:* `{uptime_pct:.2f}%`\n"
            f"💰 *Rewards:* `{rewards:,.2f} MON`\n"
            f"📈 *Session Earned:* `+{session_earned:,.4f} MON`\n"
            f"💎 *Stake:* `{stake:,.2f} MON`\n"
            f"📉 *API Timeouts:* `{api_timeouts}` blocks\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
        )
    else:
        val_section = "**🏆 Validator Stats**\n⚠️ *Awaiting Huginn API Data*\n━━━━━━━━━━━━━━━━━━━━━\n"

    gas_formatted = f"{gas_sec / 1_000_000:.1f}M" if gas_sec > 0 else "0"
    nvme_section = f"{nvme_str}\n" if nvme_str else ""
    block_time_display = f"{block_time_ms:.0f} ms" if block_time_ms > 0 else "Calculating..."

    msg = (
        f"🛡️ *{VALIDATOR_MONIKER} | MONAD WATCHDOG*\n"
        f"📅 `{now}`\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "**⛓️ Blockchain & Node**\n"
        f"🧱 *Local Block:* `{local_height}`\n"
        f"⏱️ *Block Time:* `{block_time_display}`\n"
        f"⚡ *Current TPS:* `{tps}`\n"
        f"🔥 *Gas/Sec:* `{gas_formatted}` | 💸 *Base Fee:* `{base_fee:.2f} gwei`\n"
        f"🔄 *Sync Status:* {sync_emoji} `{sync_status}`\n"
        f"🎯 *Epoch:* `{api_epoch}`\n"
        f"🔁 *Round:* `{rnd}`\n"
        f"✍️ *Node Status:* {val_status}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        + val_section +
        "**🖥️ Server Health**\n"
        f"🧠 *CPU:* `{cpu}%` | 💾 *RAM:* `{ram}%`\n"
        f"🌡️ *Temp (Gen):* `{temp_str}`\n"
        + nvme_section +
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
    print("🥷 [INFO] Ninja Log Reader started...")
    process = subprocess.Popen(['journalctl', '-u', 'monad-bft', '-f', '-n', '0'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in process.stdout:
        line_lower = line.lower()
        if "consensus timeout" in line_lower or "failed to propose" in line_lower or "missed block" in line_lower:
            missed_block_counter += 1
        elif "sending vote" in line_lower or "committed state" in line_lower:
            missed_block_counter = 0

def telegram_poller():
    """ Dedicated thread for instant Telegram response """
    print("🤖 [INFO] Telegram Poller Listener Thread started...")
    last_update_id = None
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            params = {"timeout": 5}
            if last_update_id:
                params["offset"] = last_update_id + 1
                
            response = requests.get(url, params=params, timeout=8)
            if response.status_code != 200:
                print(f"⚠️ [HTTP ERROR] Status Code: {response.status_code}")
                time.sleep(2)
                continue
                
            data = response.json()
            if not data.get("ok"):
                print(f"⚠️ [TELEGRAM API DENIED] {data.get('description')}")
                time.sleep(3)
                continue

            for result in data.get("result", []):
                last_update_id = result["update_id"]
                if "message" in result and "text" in result["message"]:
                    text = result["message"]["text"].strip()
                    chat_id = str(result["message"]["chat"]["id"])
                    
                    print(f"📩 [TELEGRAM RECV] Chat ID: {chat_id} | Text: '{text}'")
                    
                    if text == "/start":
                        send_message(chat_id, "👋 Hello! Type */status* for detailed metrics.")
                    elif text.startswith("/status"):
                        print("⚡ [/status RECV] Generating dashboard...")
                        send_message(chat_id, "🔄 Fetching dashboard...")
                        msg = create_status_message()
                        send_message(chat_id, msg)
                        print("✅ [/status SENT] Status report successfully delivered!")
        except Exception as e:
            print(f"❌ [POLLER EXCEPTION] {e}")
            time.sleep(2)

def main():
    global missed_block_counter, initial_rewards
    global cached_monad_details, cached_val_api_data, cached_epoch_details
    
    print("🚀 [INFO] Monad Ultimate Validator Watchdog started...")
    
    init_data = get_validator_api_details()
    if init_data and init_data.get('rewards'):
        initial_rewards = init_data["rewards"]
        
    # Start Log Reader Thread
    log_thread = threading.Thread(target=monitor_logs, daemon=True)
    log_thread.start()
    
    # Start Telegram Poller Thread
    tele_thread = threading.Thread(target=telegram_poller, daemon=True)
    tele_thread.start()
    
    last_height = 0
    stuck_counter = 0
    last_report_time = time.time()
    last_hardware_alert_time = 0 
    last_tps_alert_time = 0 
    last_gas_alert_time = 0
    last_fee_alert_time = 0
    
    last_monad_status_time = 0
    last_api_fetch_time = 0
    
    last_api_lag_alert_time = 0
    api_down_alerted = False
    last_stake = init_data.get("stake") if init_data else None
    
    while True:
        current_height, current_tps, current_gas_sec, current_base_fee, current_block_time_ms = get_eth_block_details()
        cpu, ram, disk_percent, disk_str, disk_io_str, temp_str, nvme_str = get_system_health()
        
        now_time = time.time()

        if now_time - last_monad_status_time > 30:
            cached_monad_details = get_monad_status_details()
            last_monad_status_time = now_time

        if now_time - last_api_fetch_time > 30:
            cached_val_api_data = get_validator_api_details()
            cached_epoch_details = get_epoch_details()
            last_api_fetch_time = now_time

        triedb_percent = cached_monad_details.get("triedb_percent")
        val_api_data = cached_val_api_data

        if val_api_data is None:
            if not api_down_alerted:
                send_alert("⚠️ **API SILENCE WARNING** ⚠️\nHuginn API is unreachable!")
                api_down_alerted = True
        else:
            if api_down_alerted:
                send_alert("✅ Huginn API connection restored.")
                api_down_alerted = False
            
            if current_height is not None and val_api_data.get("api_block_height") is not None:
                api_height = val_api_data["api_block_height"]
                lag = current_height - api_height
                if lag > API_LAG_THRESHOLD:
                    if time.time() - last_api_lag_alert_time > 3600:
                        send_alert(f"⏳ **HUGINN API LAG WARNING** ⏳\nHuginn API is lagging `{lag:,}` blocks behind!")
                        last_api_lag_alert_time = time.time()

            if "stake" in val_api_data:
                current_stake = val_api_data["stake"]
                if last_stake is not None:
                    if current_stake < last_stake:
                        dropped_amount = last_stake - current_stake
                        send_alert(f"⚠️ **STAKE DROP ALERT** ⚠️\n`{dropped_amount:,.2f} MON` was unstaked!\nCurrent Stake: `{current_stake:,.2f} MON`")
                    elif current_stake > last_stake:
                        gained_amount = current_stake - last_stake
                        send_alert(f"🎉 **STAKE INCREASE ALERT** 🎉\n`{gained_amount:,.2f} MON` was delegated!\nCurrent Stake: `{current_stake:,.2f} MON`")
                last_stake = current_stake
        
        if val_api_data and val_api_data.get("is_jailed"):
            send_alert("🚨 *CRITICAL ALERT* 🚨\n\nYour validator has been **JAILED**!")
            time.sleep(60) 

        if missed_block_counter >= ALERT_TIMEOUT_THRESHOLD:
            send_alert(f"🚨 **VALIDATOR ALERT** 🚨\nMissed `{missed_block_counter}` consecutive blocks!")
            missed_block_counter = 0 
            time.sleep(10) 

        if time.time() - last_hardware_alert_time > 300: 
            alert_msg = ""
            if cpu > ALERT_CPU_THRESHOLD: alert_msg += f"⚠️ *HIGH CPU:* `{cpu}%`\n"
            if ram > ALERT_RAM_THRESHOLD: alert_msg += f"⚠️ *HIGH RAM:* `{ram}%`\n"
            if disk_percent > ALERT_DISK_THRESHOLD: alert_msg += f"💽 *OS DISK:* `{disk_percent}%`\n"
            if triedb_percent is not None and triedb_percent > ALERT_DISK_THRESHOLD: 
                alert_msg += f"🗄️💽 *TRIEDB:* `{triedb_percent}%`\n"
            
            if "🔴" in nvme_str:
                 alert_msg += f"🔥 **NVME WEAR CRITICAL!** 💣\n"
                 
            if alert_msg:
                send_alert(f"🚨 **SYSTEM RESOURCE WARNING** 🚨\n\n{alert_msg}")
                last_hardware_alert_time = time.time()

        if current_gas_sec >= ALERT_GAS_SEC_THRESHOLD and time.time() - last_gas_alert_time > 300:
            send_alert(f"🔥 **HEAVY EXECUTION ALERT** 🔥\nNetwork burning `{current_gas_sec / 1_000_000:.1f}M` Gas/sec!")
            last_gas_alert_time = time.time()
    
        if current_base_fee >= ALERT_BASE_FEE_THRESHOLD and time.time() - last_fee_alert_time > 300:
            send_alert(f"💸 **BASE FEE SPIKE DETECTED** 💸\nFees skyrocketed to `{current_base_fee:.2f} gwei`!")
            last_fee_alert_time = time.time()

        if current_tps >= ALERT_TPS_THRESHOLD and time.time() - last_tps_alert_time > 300:
            send_alert(f"🚀 **HIGH TPS ALERT** 🚀\nNetwork reached estimated `{current_tps}` TPS!")
            last_tps_alert_time = time.time()

        if current_height is not None:
            if current_height != last_height:
                stuck_counter = 0
            else:
                stuck_counter += 1

            if stuck_counter >= 90: 
                send_alert(f"🛑 *ALERT: Node STUCK!*\nBlock: `{current_height}`\nNo new blocks for 3 minutes!")
                stuck_counter = 0 

            if time.time() - last_report_time > AUTO_REPORT_INTERVAL:
                msg = create_status_message()
                send_message(TELEGRAM_CHAT_ID, "⏰ *AUTOMATIC REPORT*\n\n" + msg)
                last_report_time = time.time()
            
            last_height = current_height
            
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()

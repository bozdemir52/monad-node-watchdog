import requests
import time
import datetime
import sys

# Import configuration safely
try:
    import config
except ImportError:
    print("❌ ERROR: config.py not found!")
    sys.exit(1)

def send_telegram_alert(message):
    """Sends a message to the configured Telegram Bot."""
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"⚠️ Telegram Error: {e}")

def get_eth_block_height():
    """Fetches block height from Ethereum RPC (Port 8080)."""
    payload = {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}
    try:
        response = requests.post(config.NODE_RPC_URL, json=payload, timeout=5)
        response.raise_for_status()
        data = response.json()
        if "result" in data:
            return int(data["result"], 16) # Hex to Int conversion
        return None
    except Exception as e:
        print(f"❌ RPC Connection Error: {e}")
        return None

def check_node():
    """Decides which check to run based on config."""
    height = get_eth_block_height()
    
    if height is not None:
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Node OK | Height: {height}")
        return {"height": height}
    
    return None

def main():
    print("🛡️ Monad Node Watchdog (EVM Mode) Started...")
    send_telegram_alert("🚀 *Monad Watchdog Active (EVM Mode)!*\nMonitoring started via Port 8080.")
    
    last_height = 0
    stuck_counter = 0
    
    while True:
        status = check_node()
        
        if status is None:
            send_telegram_alert("🚨 *CRITICAL: Node Unreachable!*\nRPC (8080) is not responding.")
        else:
            current_height = status['height']
            
            # Stall Check (Has the block height changed?)
            if current_height == last_height and current_height > 0:
                stuck_counter += 1
                if stuck_counter >= 3: # 3 minutes stuck
                    send_telegram_alert(f"🛑 *ALERT: Node STUCK!*\nHeight: {current_height}\nNo new blocks for 3 minutes.")
            else:
                stuck_counter = 0 
            
            last_height = current_height
            
        time.sleep(config.CHECK_INTERVAL)

if __name__ == "__main__":
    main()

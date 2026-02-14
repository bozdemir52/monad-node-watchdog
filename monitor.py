---

### 2. Dosya: `monitor.py`
*(Bu kodda artık şifre yok, şifreyi `config.py` dosyasından çekecek. Böylece GitHub'a atsan da güvendesin.)*

```python
import requests
import time
import datetime
import sys

# Import configuration safely
try:
    import config
except ImportError:
    print("❌ ERROR: config.py not found! Please rename 'config.py.example' to 'config.py' and fill in your details.")
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

def check_node():
    """Checks the local node status via RPC."""
    try:
        response = requests.get(config.NODE_RPC_URL, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        result = data['result']
        sync_info = result['sync_info']
        node_info = result['node_info']
        
        latest_block_height = int(sync_info['latest_block_height'])
        catching_up = sync_info['catching_up']
        moniker = node_info['moniker']
        
        # Log to terminal
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {moniker} | Height: {latest_block_height} | Sync: {'CATCHING UP' if catching_up else 'OK'}")
        
        return {
            "height": latest_block_height,
            "catching_up": catching_up,
            "moniker": moniker
        }

    except Exception as e:
        print(f"❌ RPC Connection Error: {e}")
        return None

def main():
    print("🛡️ Monad Node Watchdog Started...")
    send_telegram_alert("🚀 *Monad Watchdog Active!*\nMonitoring started successfully.")
    
    last_height = 0
    stuck_counter = 0
    
    while True:
        status = check_node()
        
        if status is None:
            send_telegram_alert("🚨 *CRITICAL: Node Unreachable!*\nCheck your server or RPC settings.")
        else:
            # 1. Sync Check
            if status['catching_up']:
                send_telegram_alert(f"⚠️ *WARNING: Node Catching Up!*\nCurrent Height: {status['height']}")
            
            # 2. Stall Check (Has the block height changed?)
            if status['height'] == last_height:
                stuck_counter += 1
                if stuck_counter >= 3: # Alert after 3 consecutive failures (approx 3 mins)
                    send_telegram_alert(f"🛑 *ALERT: Node STUCK!*\nHeight: {status['height']}\nNo new blocks for 3 minutes.")
            else:
                stuck_counter = 0 
            
            last_height = status['height']
            
        time.sleep(config.CHECK_INTERVAL)

if __name__ == "__main__":
    main()

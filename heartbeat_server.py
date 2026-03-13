import time
import threading
import requests
from flask import Flask

app = Flask(__name__)

# --- CONFIGURATION ---
DISCORD_WEBHOOK = "YOUR_DISCORD_WEBHOOK_URL_HERE"
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"
TIMEOUT_LIMIT = 180  # Time in seconds (e.g., 180 seconds = 3 minutes)

last_ping_time = time.time()
alert_sent = False

def send_alert():
    """Sends a critical alert if the main node stops sending signals"""
    msg = "🚨 **CRITICAL ALERT: Node Server is Down or Disconnected!** 🚨\n(No heartbeat received for the last 3 minutes!)"
    
    # Send to Discord
    requests.post(DISCORD_WEBHOOK, json={"content": msg})
    
    # Send to Telegram
    t_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(t_url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})

@app.route('/ping', methods=['GET'])
def ping():
    """Endpoint that receives the 'I am alive' signal from the main node"""
    global last_ping_time, alert_sent
    last_ping_time = time.time()
    
    if alert_sent:
        # Notify if the server comes back online after an outage
        recovery_msg = "✅ **INFO: Node Server has reconnected and is sending signals again!**"
        requests.post(DISCORD_WEBHOOK, json={"content": recovery_msg})
        
        t_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(t_url, json={"chat_id": TELEGRAM_CHAT_ID, "text": recovery_msg, "parse_mode": "Markdown"})
        
        alert_sent = False
        
    return "OK", 200

def check_timeout():
    """Background task that continuously checks the time passed since the last ping"""
    global alert_sent
    while True:
        time.sleep(10)
        if time.time() - last_ping_time > TIMEOUT_LIMIT and not alert_sent:
            print("[ALERT] Cannot reach the Node Server! Triggering alarms...")
            send_alert()
            alert_sent = True

if __name__ == "__main__":
    # Start the timeout checker in the background
    checker = threading.Thread(target=check_timeout, daemon=True)
    checker.start()
    
    print("🛡️ Heartbeat Server Started. Listening on port 5000...")
    app.run(host='0.0.0.0', port=5000)

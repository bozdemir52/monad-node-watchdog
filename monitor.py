import requests
import time
import datetime
import sys

# Ayarları config dosyasından al
try:
    import config
except ImportError:
    print("❌ ERROR: config.py bulunamadı!")
    sys.exit(1)

# --- AYARLAR ---
CHECK_INTERVAL = 10  # 10 Saniyede bir Telegram'ı ve Node'u kontrol et
AUTO_REPORT_INTERVAL = 4 * 60 * 60  # 4 Saatte bir otomatik rapor
# ----------------

# Global değişkenler
start_time = time.time()
last_update_id = None

def get_uptime():
    """Botun ne kadar süredir çalıştığını hesaplar"""
    seconds = time.time() - start_time
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    return f"{int(d)}d {int(h)}h {int(m)}m"

def telegram_api(method, data=None):
    """Telegram API çağrılarını yönetir"""
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{method}"
    try:
        if data:
            response = requests.post(url, data=data, timeout=10)
        else:
            response = requests.get(url, timeout=10)
        return response.json()
    except Exception as e:
        print(f"⚠️ Telegram Hatası ({method}): {e}")
        return None

def send_message(chat_id, text):
    """Mesaj gönderir"""
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    telegram_api("sendMessage", data)

def get_eth_block_height():
    """8080 Portundan Blok Yüksekliğini Alır"""
    payload = {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}
    try:
        response = requests.post(config.NODE_RPC_URL, json=payload, timeout=5)
        response.raise_for_status()
        data = response.json()
        if "result" in data:
            return int(data["result"], 16)
        return None
    except Exception as e:
        print(f"❌ RPC Bağlantı Hatası: {e}")
        return None

def create_status_message(height):
    """Havalı durum raporunu oluşturur"""
    if height is None:
        return "🚨 **HATA:** Node verisine ulaşılamıyor!"
    
    uptime = get_uptime()
    now = datetime.datetime.now().strftime('%H:%M:%S')
    
    # ITRocket benzeri, kopyalanabilir blok (monospace) tasarımı
    msg = (
        "📊 **MONAD NODE DURUMU**\n"
        f"🕐 `{now}`\n"
        "-----------------------------\n"
        f"🧱 **Blok Yüksekliği:** `{height}`\n"
        f"⏳ **Uptime:** `{uptime}`\n"
        f"📡 **Port:** `8080 (EVM)`\n"
        f"✅ **Sync Durumu:** `Senkronize`\n"
        "-----------------------------\n"
        "🤖 _/status yazarak güncelleyebilirsin._"
    )
    return msg

def check_updates():
    """Telegram'dan gelen komutları (/status) kontrol eder"""
    global last_update_id
    
    # offset parametresi ile sadece yeni mesajları alıyoruz
    params = {"timeout": 5}
    if last_update_id:
        params["offset"] = last_update_id + 1
        
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if not data.get("ok"):
            return

        for result in data.get("result", []):
            last_update_id = result["update_id"]
            
            # Mesaj var mı kontrol et
            if "message" in result and "text" in result["message"]:
                text = result["message"]["text"]
                chat_id = result["message"]["chat"]["id"]
                
                # Sadece bizim belirlediğimiz Chat ID'ye cevap ver (Güvenlik)
                if str(chat_id) == str(config.TELEGRAM_CHAT_ID):
                    if text == "/start":
                        send_message(chat_id, "👋 Merhaba! Ben Monad Bekçisi.\nDurumu görmek için **/status** yazabilirsin.")
                    elif text == "/status":
                        send_message(chat_id, "🔄 Veriler çekiliyor...")
                        height = get_eth_block_height()
                        msg = create_status_message(height)
                        send_message(chat_id, msg)

    except Exception as e:
        print(f"⚠️ Update Hatası: {e}")

def main():
    print("🛡️ Monad Watchdog (İnteraktif Mod) Başlatıldı...")
    send_message(config.TELEGRAM_CHAT_ID, "🚀 **Bot Başlatıldı!**\nKomut vermek için `/status` yazabilirsin.")
    
    last_height = 0
    stuck_counter = 0
    last_report_time = time.time()
    
    while True:
        # 1. Telegram Komutlarını Kontrol Et (ÖNEMLİ: Bu yeni kısım)
        check_updates()
        
        # 2. Node Durumunu Çek
        current_height = get_eth_block_height()
        
        if current_height is None:
            # Sadece kritik hatada log bas, sürekli mesaj atıp spam yapma
            print("❌ Node Cevap Vermiyor!")
        else:
            # --- Otomatik Rapor Zamanı ---
            if time.time() - last_report_time > AUTO_REPORT_INTERVAL:
                msg = create_status_message(current_height)
                send_message(config.TELEGRAM_CHAT_ID, "⏰ **OTOMATİK RAPOR**\n" + msg)
                last_report_time = time.time()

            # --- Node Takıldı mı Kontrolü ---
            if current_height == last_height and current_height > 0:
                stuck_counter += 1
                # Her döngü 10 saniye, 18 döngü = 3 dakika
                if stuck_counter >= 18: 
                    send_message(config.TELEGRAM_CHAT_ID, f"🛑 *ALARM: Node TAKILDI!*\nBlok: {current_height}\n3 dakikadır yeni blok yok.")
                    stuck_counter = 0 # Alarmı sıfırla ki spam yapmasın
            else:
                stuck_counter = 0 
            
            last_height = current_height
            
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()

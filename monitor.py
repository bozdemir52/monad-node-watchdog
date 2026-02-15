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
REPORT_INTERVAL = 4 * 60 * 60  # 4 Saatte bir rapor at (Saniye cinsinden)
# ----------------

def send_telegram_message(message):
    """Telegrama mesaj atma fonksiyonu"""
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown" # Mesajı süslemek için
    }
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"⚠️ Telegram Hatası: {e}")

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

def main():
    print("🛡️ Monad Watchdog (Rapor Modu) Başlatıldı...")
    
    # 1. Başlangıçta hemen bir mesaj at (Test için)
    start_msg = (
        "🤖 *Monad Bot Aktif!*\n"
        "------------------\n"
        "✅ İzleme Başladı\n"
        "📡 Port: 8080 (EVM)\n"
        "⏰ Rapor Aralığı: 4 Saat"
    )
    send_telegram_message(start_msg)
    
    last_height = 0
    stuck_counter = 0
    last_report_time = time.time()
    
    while True:
        current_height = get_eth_block_height()
        
        if current_height is None:
            # HATA DURUMU
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ❌ Node Cevap Vermiyor!")
            send_telegram_message("🚨 *ALARM: Node Ulaşılamaz!* \nLütfen sunucuyu kontrol et.")
        else:
            # NORMAL DURUM
            now = datetime.datetime.now().strftime('%H:%M:%S')
            print(f"[{now}] Node OK | Height: {current_height}")
            
            # --- Rapor Zamanı Geldi mi? ---
            if time.time() - last_report_time > REPORT_INTERVAL:
                blocks_processed = current_height - last_height if last_height > 0 else 0
                report_msg = (
                    "📊 *MONAD DURUM RAPORU*\n"
                    f"CLOCK: {now}\n"
                    "-------------------\n"
                    f"🧱 **Blok Yüksekliği:** `{current_height}`\n"
                    f"✅ **Durum:** Çalışıyor\n"
                    "-------------------\n"
                    "👮‍♂️ *Nöbetteyim, sorun yok.*"
                )
                send_telegram_message(report_msg)
                last_report_time = time.time()

            # --- Node Takıldı mı Kontrolü ---
            if current_height == last_height and current_height > 0:
                stuck_counter += 1
                if stuck_counter >= 3: # 3 dakika boyunca blok artmazsa
                    send_telegram_message(f"🛑 *ALARM: Node TAKILDI!*\nBlok: {current_height}\n3 dakikadır yeni blok yok.")
            else:
                stuck_counter = 0 
            
            last_height = current_height
            
        time.sleep(config.CHECK_INTERVAL)

if __name__ == "__main__":
    main()

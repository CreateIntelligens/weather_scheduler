import time
import httpx
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime
from opencc import OpenCC

# 後端 API 的網址 (在 Docker 網路中，host 名稱通常是 service name)
# 這裡預設為 weather-backend，這是我們在 docker-compose 中定義的服務名稱
BACKEND_URL = "http://weather-backend:8000/api/weather?refresh=true"
TTS_API_URL = "http://10.9.0.35:5456/api/stream-speak"
TTS_ENGINE = "indextts" # Options: "indextts", "edgetts", etc.

def send_to_tts_api(text):
    """將 AI 報告發送到 TTS 服務"""
    print(f"[{datetime.now()}] Sending report to TTS API (Engine: {TTS_ENGINE})...")
    
    # # 若使用 indextts，需將繁體中文轉為簡體中文
    # if TTS_ENGINE == "indextts":
    #     try:
    #         print(f"[{datetime.now()}] Original (Traditional): {text[:100]}...")
    #         cc = OpenCC('t2s') # t2s: Traditional to Simplified
    #         text = cc.convert(text)
    #         print(f"[{datetime.now()}] Converted (Simplified): {text[:100]}...")
    #         print(f"[{datetime.now()}] Converted text to Simplified Chinese for indextts.")
    #     except Exception as e:
    #         print(f"[{datetime.now()}] OpenCC Conversion Error: {e}")

    try:
        # 根據您的需求，包含 engine 欄位，值固定為 indextts
        payload = {
            "engine": TTS_ENGINE, 
            "text": text
        }
        
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(TTS_API_URL, json=payload)
            if resp.status_code == 200:
                print(f"[{datetime.now()}] TTS API Sent SUCCESS!")
            else:
                print(f"[{datetime.now()}] TTS API Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[{datetime.now()}] TTS API Connection Error: {e}")

def job_update_weather():
    print(f"[{datetime.now()}] Triggering scheduled weather update...")
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.get(BACKEND_URL)
            if resp.status_code == 200:
                data = resp.json()
                cities_count = len(data.get("cities", []))
                ai_report = data.get("ai_report", "")
                ai_report_preview = ai_report[:50] + "..."
                
                print(f"[{datetime.now()}] Update SUCCESS!")
                print(f" -> Cities Fetched: {cities_count}")
                print(f" -> AI Report Preview: {ai_report_preview}")
                
                # 成功後，轉發給 TTS API
                if ai_report:
                    send_to_tts_api(ai_report)
            else:
                print(f"[{datetime.now()}] Update failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[{datetime.now()}] Connection error: {e}")

if __name__ == "__main__":
    print("Starting Weather Scheduler...")
    
    # 建立排程器
    scheduler = BlockingScheduler()
    
    # 設定排程：每小時的第 0 分鐘執行 (cron style)
    # 這樣會確保在 1:00, 2:00, 3:00... 準時執行
    scheduler.add_job(job_update_weather, 'cron', minute=0)
    
    # 程式啟動時先立即執行一次，確保快取是熱的
    # 加入重試機制，因為後端可能還沒完全啟動
    max_retries = 12 # 嘗試 1 分鐘 (12 * 5s)
    for i in range(max_retries):
        try:
            print(f"Initial update attempt {i+1}/{max_retries}...")
            # 這裡我們稍微修改一下 job_update_weather 的行為，讓它拋出異常以便重試
            with httpx.Client(timeout=60.0) as client:
                resp = client.get(BACKEND_URL)
                if resp.status_code == 200:
                    print(f"[{datetime.now()}] Initial update successful!")
                    break
                else:
                    print(f"Update failed with status {resp.status_code}")
        except Exception as e:
            print(f"Connection failed ({e}), retrying in 5 seconds...")
            time.sleep(5)
    else:
        print("Warning: Initial update failed after multiple attempts. Scheduler will continues to run for next hour.")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass

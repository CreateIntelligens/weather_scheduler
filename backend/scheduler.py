import time
import httpx
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime

# Backend 內部 URL
BACKEND_BASE_URL = "http://weather-backend:8000"
UPDATE_WEATHER_URL = f"{BACKEND_BASE_URL}/api/weather?refresh=true"
CHECK_WARNINGS_URL = f"{BACKEND_BASE_URL}/api/cron/check-warnings"
CHECK_EARTHQUAKES_URL = f"{BACKEND_BASE_URL}/api/cron/check-earthquakes"

TTS_API_URL = "http://10.9.0.35:5456/api/stream-speak"
TTS_ENGINE = "indextts"

def send_to_tts_api(text):
    """(Legacy) 直接發送 TTS，現主要由 Backend 處理，但在一般天氣更新時仍保留此邏輯"""
    print(f"[{datetime.now()}] Sending report to TTS API (Engine: {TTS_ENGINE})...")
    try:
        payload = {"engine": TTS_ENGINE, "text": text}
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(TTS_API_URL, json=payload)
            if resp.status_code == 200:
                print(f"[{datetime.now()}] TTS API Sent SUCCESS!")
            else:
                print(f"[{datetime.now()}] TTS API Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[{datetime.now()}] TTS API Connection Error: {e}")

def job_update_weather():
    """每小時更新一般天氣"""
    print(f"[{datetime.now()}] [Job] Triggering hourly weather update...")
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.get(UPDATE_WEATHER_URL)
            if resp.status_code == 200:
                data = resp.json()
                ai_report = data.get("ai_report", "")
                print(f"[{datetime.now()}] Weather update SUCCESS. AI Report length: {len(ai_report)}")
                # 一般天氣更新後，仍需在此處呼叫 TTS，因為 Backend 的 GET /api/weather 不會主動播報
                if ai_report:
                    send_to_tts_api(ai_report)
            else:
                print(f"[{datetime.now()}] Weather update failed: {resp.status_code}")
    except Exception as e:
        print(f"[{datetime.now()}] Weather update connection error: {e}")

def job_check_warnings():
    """每 10 分鐘檢查是否有新特報"""
    print(f"[{datetime.now()}] [Job] Checking for weather warnings...")
    try:
        with httpx.Client(timeout=60.0) as client:
            # 使用 POST 觸發後端的檢查邏輯
            resp = client.post(CHECK_WARNINGS_URL)
            if resp.status_code == 200:
                result = resp.json()
                count = result.get("new_warnings_processed", 0)
                print(f"[{datetime.now()}] Warning check complete. New warnings processed: {count}")
            else:
                print(f"[{datetime.now()}] Warning check failed: {resp.status_code}")
    except Exception as e:
        print(f"[{datetime.now()}] Warning check connection error: {e}")

def job_check_earthquakes():
    """每 1 分鐘檢查是否有新地震"""
    print(f"[{datetime.now()}] [Job] Checking for earthquakes...")
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(CHECK_EARTHQUAKES_URL)
            if resp.status_code == 200:
                result = resp.json()
                count = result.get("new_earthquakes_processed", 0)
                print(f"[{datetime.now()}] Earthquake check complete. New eqs processed: {count}")
            else:
                print(f"[{datetime.now()}] Earthquake check failed: {resp.status_code}")
    except Exception as e:
        print(f"[{datetime.now()}] Earthquake check connection error: {e}")

if __name__ == "__main__":
    print("Starting Weather Scheduler...")
    
    scheduler = BlockingScheduler()
    
    # 優先順序調整：
    # 1. 每 1 分鐘執行地震檢查 (最緊急)
    scheduler.add_job(job_check_earthquakes, 'cron', minute='*')

    # 2. 每 10 分鐘執行特報檢查 (次緊急)
    scheduler.add_job(job_check_warnings, 'cron', minute='*/10')

    # 3. 每小時整點執行一般天氣預報 (例行性)
    scheduler.add_job(job_update_weather, 'cron', minute=0)
    
    # 程式啟動時，先等待 Backend Ready，然後立即執行一次檢查
    print("Waiting for backend to be ready...")
    time.sleep(10) # 等待 Backend 與 DB 連線建立
    
    # 立即執行一次特報檢查
    job_check_warnings()
    job_check_earthquakes()
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
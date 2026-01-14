import os
import json
import httpx
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

# DB imports
from database import engine, Base, get_db
import models

# 初始化資料庫 Table
models.Base.metadata.create_all(bind=engine)

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config
CWA_API_KEY = os.getenv("CWA_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()
AI_MODEL = os.getenv("AI_MODEL", "gemini-1.5-flash")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

TTS_API_URL = "http://10.9.0.35:5456/api/stream-speak"
TTS_ENGINE = "indextts"

TARGET_CITIES = [
    '基隆市', '臺北市', '新北市', '桃園市', '新竹市', '新竹縣', '苗栗縣', '臺中市',
    '彰化縣', '南投縣', '雲林縣', '嘉義市', '嘉義縣', '臺南市', '高雄市', '屏東縣',
    '宜蘭縣', '花蓮縣', '臺東縣', '澎湖縣', '金門縣', '連江縣'
]

# --- Pydantic Models ---

class CityWeather(BaseModel):
    name: str
    wx: str
    pop: str
    minT: str
    maxT: str

class WeatherResponse(BaseModel):
    overview: str
    cities: List[CityWeather]
    ai_report: str

class WarningRecord(BaseModel):
    id: int
    title: str
    issue_time: str
    content: str
    affected_areas: str
    ai_report: Optional[str] = None
    created_at: datetime

    class Config:
        orm_mode = True

# --- Helper Functions ---

async def send_to_tts_api(text: str):
    """將文字發送到 TTS 服務"""
    print(f"[{datetime.now()}] Sending to TTS API...")
    try:
        payload = {"engine": TTS_ENGINE, "text": text}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(TTS_API_URL, json=payload)
            if resp.status_code == 200:
                print("TTS API Sent SUCCESS!")
            else:
                print(f"TTS API Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"TTS API Connection Error: {e}")

async def generate_ai_text(system_prompt: str, user_content: str) -> str:
    """呼叫 AI 生成文字 (通用函式)"""
    async with httpx.AsyncClient() as client:
        try:
            if AI_PROVIDER == "openai":
                if not OPENAI_API_KEY: return "未設定 OpenAI API Key"
                url = "https://api.openai.com/v1/chat/completions"
                headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
                payload = {
                    "model": AI_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ]
                }
                resp = await client.post(url, headers=headers, json=payload, timeout=30.0)
                resp.raise_for_status()
                result_text = resp.json()["choices"][0]["message"]["content"]
                print(f"\n[AI REPORT GENERATED ({AI_PROVIDER})]:\n{'-'*20}\n{result_text}\n{'-'*20}\n")
                return result_text

            elif AI_PROVIDER == "groq":
                if not GROQ_API_KEY: return "未設定 Groq API Key"
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
                payload = {
                    "model": AI_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ]
                }
                resp = await client.post(url, headers=headers, json=payload, timeout=30.0)
                resp.raise_for_status()
                result_text = resp.json()["choices"][0]["message"]["content"]
                print(f"\n[AI REPORT GENERATED ({AI_PROVIDER})]:\n{'-'*20}\n{result_text}\n{'-'*20}\n")
                return result_text

            else: # Default to Gemini
                if not GEMINI_API_KEY: return "未設定 Gemini Key"
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{AI_MODEL}:generateContent?key={GEMINI_API_KEY}"
                full_prompt = system_prompt + "\n" + user_content
                resp = await client.post(
                    url, 
                    json={"contents": [{"parts": [{"text": full_prompt}]}]},
                    timeout=20.0
                )
                resp.raise_for_status()
                data = resp.json()
                result_text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "AI 生成失敗")
                
                # --- LOGGING FULL AI REPORT ---
                print(f"\n[AI REPORT GENERATED ({AI_PROVIDER})]:\n{'-'*20}\n{result_text}\n{'-'*20}\n")
                
                return result_text

        except Exception as e:
            print(f"AI Generation Error ({AI_PROVIDER}): {str(e)}")
            return "AI 分析暫時無法使用。"

async def fetch_overview(client: httpx.AsyncClient) -> str:
    """(保留) 抓取全臺天氣概況"""
    return ""

async def fetch_cities_forecast(client: httpx.AsyncClient) -> List[CityWeather]:
    """抓取各縣市預報 (F-C0032-001)"""
    if not CWA_API_KEY:
        return []

    locations = ",".join(TARGET_CITIES)
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001?Authorization={CWA_API_KEY}&format=JSON&locationName={locations}"
    
    cities_data = []
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        raw_locations = data.get("records", {}).get("location", [])

        for loc in raw_locations:
            weather_elements = loc.get("weatherElement", [])
            
            def get_val(name):
                el = next((e for e in weather_elements if e["elementName"] == name), None)
                if el and el.get("time") and len(el["time"]) > 0:
                    return el["time"][0]["parameter"]["parameterName"]
                return "-"

            cities_data.append(CityWeather(
                name=loc["locationName"],
                wx=get_val("Wx"),
                pop=get_val("PoP"),
                minT=get_val("MinT"),
                maxT=get_val("MaxT")
            ))
    except Exception as e:
        print(f"Error fetching cities: {e}")
        
    return cities_data

# --- API Endpoints ---

# 1. 既有的天氣預報 API
weather_cache = {"data": None, "last_updated": None}

@app.get("/api/weather", response_model=WeatherResponse)
async def get_weather(refresh: bool = False):
    global weather_cache
    now = datetime.now()
    
    if not refresh and weather_cache["data"] and weather_cache["last_updated"]:
        if now - weather_cache["last_updated"] < timedelta(minutes=55):
            print("Using cached weather data")
            return weather_cache["data"]

    print("Fetching fresh weather data...")
    async with httpx.AsyncClient() as client:
        overview = await fetch_overview(client)
        cities = await fetch_cities_forecast(client)
        
        # 一般天氣預報的 Prompt
        cities_summary = "\n".join([f"{c.name}: {c.wx}, {c.minT}-{c.maxT}度, 降雨{c.pop}%" for c in cities])
        system_prompt = """
        你現在是一位專業且精準的氣象分析師。請根據以下資料撰寫最新的整點氣象快訊。
    
        【嚴格要求】:
        1. **絕對不要**使用任何寒暄語或開場白。
        2. **直接切入**天氣重點。
        3. 語氣要像即時通訊軟體中的「重點整理」一樣，簡潔有力但保有專業度。
        4. 請根據數據分析目前是受什麼天氣系統（如東北季風、鋒面）影響。
        5. 針對接下來 1-3 小時做簡單的穿著或攜帶雨具建議。
        6. 字數約 200-250 字。
        """
        user_content = f"【輸入資料】:\n{cities_summary}"
        
        ai_report = await generate_ai_text(system_prompt, user_content)
        
        response_data = WeatherResponse(overview=overview, cities=cities, ai_report=ai_report)
        weather_cache["data"] = response_data
        weather_cache["last_updated"] = now
        
        return response_data

@app.post("/api/weather/broadcast")
async def manual_weather_broadcast():
    """
    手動觸發：抓取最新天氣、生成 AI 報告並立即語音播報
    """
    print(f"[{datetime.now()}] Manually triggering weather broadcast...")
    async with httpx.AsyncClient() as client:
        overview = await fetch_overview(client)
        cities = await fetch_cities_forecast(client)
        
        cities_summary = "\n".join([f"{c.name}: {c.wx}, {c.minT}-{c.maxT}度, 降雨{c.pop}%" for c in cities])
        system_prompt = """
        你現在是一位專業且精準的氣象分析師。請根據以下資料撰寫最新的整點氣象快訊。
    
        【嚴格要求】:
        1. **絕對不要**使用任何寒暄語或開場白。
        2. **直接切入**天氣重點。
        3. 語氣要像即時通訊軟體中的「重點整理」一樣，簡潔有力但保有專業度。
        4. 請根據數據分析目前是受什麼天氣系統（如東北季風、鋒面）影響。
        5. 針對接下來 1-3 小時做簡單的穿著或攜帶雨具建議。
        6. 字數約 200-250 字。
        """
        user_content = f"【最新觀測資料】:\n{cities_summary}"
        
        ai_report = await generate_ai_text(system_prompt, user_content)
        
        # 立即播報
        await send_to_tts_api(ai_report)
        
        return {"status": "success", "ai_report": ai_report}

@app.get("/api/weather/{city_name}", response_model=CityWeather)
async def get_city_weather(city_name: str):
    async with httpx.AsyncClient() as client:
        if not CWA_API_KEY: raise HTTPException(status_code=500, detail="未設定 CWA API Key")
        url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001?Authorization={CWA_API_KEY}&format=JSON&locationName={city_name}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            location = data.get("records", {}).get("location", [])
            if not location: raise HTTPException(status_code=404, detail="找不到縣市")
            loc = location[0]
            weather_elements = loc.get("weatherElement", [])
            def get_val(name):
                el = next((e for e in weather_elements if e["elementName"] == name), None)
                return el["time"][0]["parameter"]["parameterName"] if el and el.get("time") else "-"
            return CityWeather(name=loc["locationName"], wx=get_val("Wx"), pop=get_val("PoP"), minT=get_val("MinT"), maxT=get_val("MaxT"))
        except Exception as e:
             raise HTTPException(status_code=500, detail=str(e))

# 2. 新增：查詢歷史特報
@app.get("/api/warnings", response_model=List[WarningRecord])
def get_warnings(limit: int = 10, db: Session = Depends(get_db)):
    warnings = db.query(models.WeatherWarning).order_by(models.WeatherWarning.created_at.desc()).limit(limit).all()
    return warnings

# 2.1 新增：手動重新播報特報
@app.post("/api/warnings/{warning_id}/re-report")
async def re_report_warning(warning_id: int, db: Session = Depends(get_db)):
    """
    手動觸發：重新生成 AI 報告並播報特定的特報 ID
    """
    warning = db.query(models.WeatherWarning).filter(models.WeatherWarning.id == warning_id).first()
    if not warning:
        raise HTTPException(status_code=404, detail="找不到該特報 ID")

    print(f"[{datetime.now()}] Manually re-reporting warning: {warning.title}")

    system_prompt = """
    你現在是一位專業的氣象主播，負責即時插播氣象特報。
    請根據接收到的氣象局特報資料，撰寫一段廣播稿。
    1. **絕對不要**使用任何寒暄語或開場白。
    2. 開頭直接切入重點。
    3. 口語化改寫時間與內容。
    4. 強調受影響地區。
    5. 簡潔扼要，約 200-250 字。
    """
    
    user_prompt = f"""
    【特報資料】
    標題: {warning.title}
    發布時間: {warning.issue_time}
    受影響地區: {warning.affected_areas}
    內容全文: {warning.content}
    """
    
    # 重新生成 AI 報告
    ai_report = await generate_ai_text(system_prompt, user_prompt)
    
    # 重新呼叫 TTS
    await send_to_tts_api(ai_report)
    
    # 更新 DB 內容
    warning.ai_report = ai_report
    db.commit()
    
    return {"status": "success", "ai_report": ai_report}

# 3. 新增：排程器呼叫的檢查端點
@app.post("/api/cron/check-warnings")
async def check_and_process_warnings(db: Session = Depends(get_db)):
    """
    抓取特報 -> 比對 DB -> 若無則生成 AI 報告並播報 -> 存入 DB
    """
    print(f"[{datetime.now()}] Checking for new warnings...")
    if not CWA_API_KEY:
        return {"status": "error", "message": "No CWA API Key"}

    # W-C0033-002: 各類特報
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/W-C0033-002?Authorization={CWA_API_KEY}&format=JSON"
    
    new_warnings_count = 0
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            
            records = data.get("records", {}).get("record", [])
            if not isinstance(records, list):
                records = [records] # 處理單筆可能是 dict 的情況

            for record in records:
                dataset_info = record.get("datasetInfo", {})
                dataset_desc = dataset_info.get("datasetDescription", "未分類特報") # Title
                issue_time = dataset_info.get("issueTime", "")
                
                # 取得內容與地區
                contents = record.get("contents", {}).get("content", {})
                content_text = contents.get("contentText", "")
                
                # 取得受影響地區
                affected_areas = []
                hazards = record.get("hazardConditions", {}).get("hazards", {}).get("hazard", [])
                if not isinstance(hazards, list): hazards = [hazards]
                
                for h in hazards:
                    info = h.get("info", {})
                    locations = info.get("affectedAreas", {}).get("location", [])
                    if not isinstance(locations, list): locations = [locations]
                    for loc in locations:
                        if "locationName" in loc:
                            affected_areas.append(loc["locationName"])
                
                affected_areas_str = ", ".join(affected_areas)

                # --- 檢查 DB 是否已存在 ---
                exists = db.query(models.WeatherWarning).filter(
                    models.WeatherWarning.issue_time == issue_time,
                    models.WeatherWarning.title == dataset_desc
                ).first()

                if exists:
                    print(f"Warning already exists: {dataset_desc} ({issue_time})")
                    continue

                # --- 這是新特報 ---
                print(f"New Warning Found: {dataset_desc}")
                
                # 生成 AI 廣播稿
                system_prompt = """
                你現在是一位專業的氣象主播，負責即時插播氣象特報。
                請根據接收到的氣象局特報資料，撰寫一段廣播稿。

                【撰寫要求】
                1. 開頭直接切入重點 (如「氣象署發布...」)。
                2. 口語化改寫：去除公文式標號，將時間改為自然口語 (如「今天上午」)。
                3. 強調受影響區域：清楚唸出受影響的縣市。
                4. 簡潔扼要：保留危險原因與防範措施，約 100-150 字。
                5. 語氣：急切、權威、清晰。
                """
                
                user_prompt = f"""
                【特報資料】
                標題: {dataset_desc}
                發布時間: {issue_time}
                受影響地區: {affected_areas_str}
                內容全文: {content_text}
                """
                
                ai_report = await generate_ai_text(system_prompt, user_prompt)
                
                # 呼叫 TTS
                await send_to_tts_api(ai_report)
                
                # 存入 DB
                new_warning = models.WeatherWarning(
                    dataset_id="W-C0033-002",
                    issue_time=issue_time,
                    title=dataset_desc,
                    content=content_text,
                    affected_areas=affected_areas_str,
                    ai_report=ai_report,
                    is_reported=True
                )
                db.add(new_warning)
                db.commit()
                new_warnings_count += 1
                
    except Exception as e:
        print(f"Error processing warnings: {e}")
        return {"status": "error", "message": str(e)}

    return {"status": "success", "new_warnings_processed": new_warnings_count}

@app.get("/")
def read_root():
    return {"status": "ok", "service": "Weather Backend"}
import os
import json
import asyncio
import httpx
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import or_, cast, String, text
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# DB imports
from database import engine, Base, get_db
import models

# 初始化資料庫 Table
models.Base.metadata.create_all(bind=engine)

def ensure_warning_columns():
    """補齊舊資料表缺少的欄位，避免沒有 migration 工具時啟動失敗。"""
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE weather_warnings ADD COLUMN IF NOT EXISTS valid_time_start VARCHAR"))
        conn.execute(text("ALTER TABLE weather_warnings ADD COLUMN IF NOT EXISTS valid_time_end VARCHAR"))
        conn.execute(text("ALTER TABLE weather_warnings ADD COLUMN IF NOT EXISTS update_time VARCHAR"))

ensure_warning_columns()

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

TTS_API_URL = os.getenv("TTS_API_URL", "http://127.0.0.1:5456/api/stream-speak")
TTS_ENGINE = os.getenv("TTS_ENGINE", "indextts")
OVERVIEW_FALLBACK_URL = os.getenv(
    "OVERVIEW_FALLBACK_URL",
    "https://cwaopendata.s3.ap-northeast-1.amazonaws.com/Forecast/F-C0032-031.FW50"
)
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Taipei")
APP_TZ = ZoneInfo(APP_TIMEZONE)

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
    valid_time_start: Optional[str] = None
    valid_time_end: Optional[str] = None
    update_time: Optional[str] = None
    content: str
    affected_areas: str
    ai_report: Optional[str] = None
    created_at: datetime

    class Config:
        orm_mode = True

class EarthquakeRecord(BaseModel):
    id: int
    earthquake_no: int
    report_type: str
    origin_time: str
    location: str
    magnitude: str
    content: str
    intensity_summary: Optional[str] = None
    ai_report: Optional[str] = None
    created_at: datetime

    class Config:
        orm_mode = True

class ForecastRecord(BaseModel):
    id: int
    report_time: datetime
    overview: Optional[str] = None
    ai_report: Optional[str] = None
    created_at: datetime

    class Config:
        orm_mode = True

# --- Helper Functions ---

def now_local() -> datetime:
    return datetime.now(APP_TZ)

async def fetch_json_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    retries: int = 3,
    timeout: float = 20.0,
    label: str = "CWA API"
):
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            resp = await client.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            last_error = e
            should_retry = True

            if isinstance(e, httpx.HTTPStatusError):
                status = e.response.status_code
                should_retry = status in (502, 503, 504)

            if attempt < retries and should_retry:
                print(f"{label} attempt {attempt}/{retries} failed: {repr(e)}. Retrying...")
                await asyncio.sleep(attempt)
                continue
            break

    raise RuntimeError(f"{label} unavailable after {retries} attempts: {repr(last_error)}")

def parse_date_range(start_date: Optional[str], end_date: Optional[str]):
    start_dt = None
    end_dt = None

    try:
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=APP_TZ)
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=APP_TZ) + timedelta(days=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式錯誤，請使用 YYYY-MM-DD")

    return start_dt, end_dt

def decode_cwa_overview_text(raw_bytes: bytes) -> str:
    """CWA 小幫手文字檔目前為 Big5/CP950 編碼。"""
    for encoding in ("cp950", "big5", "utf-8"):
        try:
            return raw_bytes.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("latin1", errors="ignore").strip()

def clean_overview_text(raw_text: str) -> str:
    """只做最小清洗：去除明顯噪音，不假設固定段落結構。"""
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("ht\ntps://", "https://")
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped == "1":
            continue
        if stripped.startswith("https://") or stripped.startswith("http://"):
            continue
        lines.append(line.rstrip())

    cleaned = "\n".join(lines)
    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n\n", "\n\n")
    return cleaned.strip()

def extract_overview_publish_time(overview: str) -> str:
    for line in overview.splitlines():
        stripped = line.strip()
        if stripped.startswith("發布時間："):
            return stripped.replace("發布時間：", "", 1).strip()
    return "未提供"

def build_weather_prompt(overview: str, cities_summary: str, current_time: str) -> tuple[str, str]:
    system_prompt = """
    你現在是一位專業且保守的氣象播報員。請根據提供的官方概要與縣市預報資料，整理一段整點天氣重點。

    【嚴格要求】
    1. **絕對不要**使用寒暄語或開場白。
    2. **優先以官方概要內容為主**，22 縣市資料只用來補充區域差異、溫度與降雨機率。
    3. 若官方概要沒有提到特定天氣系統，**禁止自行推測**或補上「東北季風、鋒面、太平洋高壓、華南雲雨區」等說法。
    4. 若官方概要與縣市資料看起來有些微差異，請以官方概要的整體判斷為主。
    5. 你會同時收到「目前播報時間」與「官方概要發布時間」，請以**目前播報時間**為基準理解「今天、今晚、晚起、明天」等相對時間。
    6. 只要使用相對日期詞，**一定要帶上日期**，例如「今（7）日」、「明（8）日晚上」；禁止單獨出現「今天、今日、明天、今晚」等沒有日期的寫法。
    7. 請整理成「全台概況 -> 降雨較明顯區域 -> 溫度/外出提醒」的順序。
    8. 建議內容要保守、實用，不要把資料沒有提供的資訊寫進去。
    9. 空氣品質、網址等非主要天氣資訊可忽略。
    10. 若颱風資訊明確表示距離臺灣遙遠或對天氣無直接影響，請不要當作播報主重點。
    11. 字數約 70-110 字，優先精簡，不要贅述重複資訊。
    """

    if overview:
        overview_publish_time = extract_overview_publish_time(overview)
        user_content = (
            f"【目前播報時間】\n{current_time}\n\n"
            f"【官方概要發布時間】\n{overview_publish_time}\n\n"
            f"【官方概要】\n{overview}\n\n"
            f"【22縣市預報資料】\n{cities_summary}"
        )
    else:
        system_prompt = """
        你現在是一位專業且保守的氣象播報員。請根據提供的縣市預報資料，整理一段整點天氣重點。

        【嚴格要求】
        1. **絕對不要**使用寒暄語或開場白。
        2. 只可根據提供的資料描述天氣現象、降雨機率與溫度差異。
        3. **禁止自行推測**天氣系統成因；不要使用「東北季風、鋒面、太平洋高壓、華南雲雨區」等說法。
        4. 你會收到目前播報時間，請以該時間為基準整理接下來的提醒。
        5. 只要使用相對日期詞，**一定要帶上日期**，例如「今（7）日」、「明（8）日晚上」；禁止單獨出現「今天、今日、明天、今晚」等沒有日期的寫法。
        6. 請整理成「全台概況 -> 降雨較明顯區域 -> 溫度/外出提醒」的順序。
        7. 建議內容要保守、實用，不要把資料沒有提供的資訊寫進去。
        8. 字數約 70-100 字，優先精簡，不要贅述重複資訊。
        """
        user_content = f"【目前播報時間】\n{current_time}\n\n【22縣市預報資料】\n{cities_summary}"

    return system_prompt, user_content

async def send_to_tts_api(text: str):
    """將文字發送到 TTS 服務"""
    print(f"[{now_local()}] Sending to TTS API...")
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
    """抓取全臺天氣小幫手概要，直接讀取目前可用的 ProductURL。"""
    try:
        overview_resp = await client.get(OVERVIEW_FALLBACK_URL, timeout=20.0)
        overview_resp.raise_for_status()
        overview_text = clean_overview_text(decode_cwa_overview_text(overview_resp.content))
        print(f"Fetched overview text length: {len(overview_text)}")
        return overview_text
    except Exception as e:
        print(f"Error fetching overview text: {e}")
        return ""

async def fetch_cities_forecast(client: httpx.AsyncClient) -> List[CityWeather]:
    """抓取各縣市預報 (F-C0032-001)"""
    if not CWA_API_KEY:
        return []

    locations = ",".join(TARGET_CITIES)
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001?Authorization={CWA_API_KEY}&format=JSON&locationName={locations}"
    
    cities_data = []
    try:
        data = await fetch_json_with_retry(client, url, timeout=20.0, label="CWA forecast API")
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
        print(f"Error fetching cities: {repr(e)}")
        
    return cities_data

# --- API Endpoints ---

# 1. 既有的天氣預報 API
weather_cache = {"data": None, "last_updated": None}

@app.get("/api/weather", response_model=WeatherResponse)
async def get_weather(refresh: bool = False, db: Session = Depends(get_db)):
    global weather_cache
    now = now_local()
    
    # --- 1. 如果不是強制更新，先從 DB 抓取最新的一筆紀錄 ---
    if not refresh:
        latest_forecast = db.query(models.WeatherForecast).order_by(models.WeatherForecast.created_at.desc()).first()
        if latest_forecast:
            print(f"Returning latest forecast from DB (ID: {latest_forecast.id})")
            try:
                cities_list = json.loads(latest_forecast.cities_data)
                return WeatherResponse(
                    overview=latest_forecast.overview or "",
                    cities=[CityWeather(**c) for c in cities_list],
                    ai_report=latest_forecast.ai_report or ""
                )
            except Exception as e:
                print(f"Error parsing DB cities_data: {e}")
                # 失敗則往下走抓取邏輯

    # --- 2. 抓取新資料並生成 AI 報告 (只有 refresh=True 或 DB 為空時執行) ---
    print("Fetching fresh weather data and generating AI report...")
    async with httpx.AsyncClient() as client:
        current_time = now.strftime("%Y-%m-%d %H:%M:%S")
        overview = await fetch_overview(client)
        cities = await fetch_cities_forecast(client)
        if not cities:
            raise HTTPException(status_code=503, detail="CWA 預報資料暫時無法取得，未生成新預報")
        
        cities_summary = "\n".join([f"{c.name}: {c.wx}, {c.minT}-{c.maxT}度, 降雨{c.pop}%" for c in cities])
        system_prompt, user_content = build_weather_prompt(overview, cities_summary, current_time)
        
        ai_report = await generate_ai_text(system_prompt, user_content)
        
        response_data = WeatherResponse(overview=overview, cities=cities, ai_report=ai_report)
        weather_cache["data"] = response_data
        weather_cache["last_updated"] = now
        
        # Save to DB
        try:
            cities_json = json.dumps([c.dict() for c in cities], ensure_ascii=False)
            new_forecast = models.WeatherForecast(
                overview=overview,
                cities_data=cities_json,
                ai_report=ai_report
            )
            db.add(new_forecast)
            db.commit()
            print(f"Saved fresh forecast to DB with ID: {new_forecast.id}")
        except Exception as e:
            print(f"Error saving forecast to DB: {e}")

        return response_data

@app.get("/api/forecasts", response_model=List[ForecastRecord])
def get_forecasts(
    skip: int = 0,
    limit: int = 10,
    q: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.WeatherForecast)
    start_dt, end_dt = parse_date_range(start_date, end_date)
    
    if q:
        search = f"%{q}%"
        query = query.filter(or_(
            models.WeatherForecast.ai_report.ilike(search),
            models.WeatherForecast.overview.ilike(search),
            models.WeatherForecast.cities_data.ilike(search)
        ))

    if start_dt:
        query = query.filter(models.WeatherForecast.report_time >= start_dt)
    if end_dt:
        query = query.filter(models.WeatherForecast.report_time < end_dt)
    
    forecasts = query.order_by(models.WeatherForecast.created_at.desc()).offset(skip).limit(limit).all()
    return forecasts

@app.get("/api/config")
def get_config():
    """回傳後端設定資訊"""
    return {
        "ai_provider": AI_PROVIDER,
        "ai_model": AI_MODEL
    }

@app.post("/api/weather/broadcast")
async def manual_weather_broadcast(db: Session = Depends(get_db)):
    """
    手動觸發：抓取最新天氣、生成 AI 報告並立即語音播報
    """
    print(f"[{now_local()}] Manually triggering weather broadcast...")
    async with httpx.AsyncClient() as client:
        current_time = now_local().strftime("%Y-%m-%d %H:%M:%S")
        overview = await fetch_overview(client)
        cities = await fetch_cities_forecast(client)
        if not cities:
            raise HTTPException(status_code=503, detail="CWA 預報資料暫時無法取得，未執行播報")
        
        cities_summary = "\n".join([f"{c.name}: {c.wx}, {c.minT}-{c.maxT}度, 降雨{c.pop}%" for c in cities])
        system_prompt, user_content = build_weather_prompt(overview, cities_summary, current_time)
        
        ai_report = await generate_ai_text(system_prompt, user_content)
        
        # 立即播報
        await send_to_tts_api(ai_report)
        
        # Save to DB
        try:
            # Serialize cities data to JSON string for storage
            cities_json = json.dumps([c.dict() for c in cities], ensure_ascii=False)
            
            new_forecast = models.WeatherForecast(
                overview=overview,
                cities_data=cities_json,
                ai_report=ai_report
            )
            db.add(new_forecast)
            db.commit()
            print(f"Saved manual broadcast forecast to DB with ID: {new_forecast.id}")
        except Exception as e:
            print(f"Error saving forecast to DB: {e}")
        
        return {"status": "success", "ai_report": ai_report}

@app.get("/api/weather/{city_name}", response_model=CityWeather)
async def get_city_weather(city_name: str):
    async with httpx.AsyncClient() as client:
        if not CWA_API_KEY: raise HTTPException(status_code=500, detail="未設定 CWA API Key")
        url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001?Authorization={CWA_API_KEY}&format=JSON&locationName={city_name}"
        try:
            data = await fetch_json_with_retry(client, url, timeout=20.0, label="CWA city forecast API")
            location = data.get("records", {}).get("location", [])
            if not location: raise HTTPException(status_code=404, detail="找不到縣市")
            loc = location[0]
            weather_elements = loc.get("weatherElement", [])
            def get_val(name):
                el = next((e for e in weather_elements if e["elementName"] == name), None)
                return el["time"][0]["parameter"]["parameterName"] if el and el.get("time") else "-"
            return CityWeather(name=loc["locationName"], wx=get_val("Wx"), pop=get_val("PoP"), minT=get_val("MinT"), maxT=get_val("MaxT"))
        except RuntimeError as e:
             raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
             raise HTTPException(status_code=500, detail=str(e))

# 2. 新增：查詢歷史特報
@app.get("/api/warnings", response_model=List[WarningRecord])
def get_warnings(
    skip: int = 0,
    limit: int = 10,
    q: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.WeatherWarning)
    start_dt, end_dt = parse_date_range(start_date, end_date)
    
    if q:
        search = f"%{q}%"
        query = query.filter(or_(
            models.WeatherWarning.title.ilike(search),
            models.WeatherWarning.content.ilike(search),
            models.WeatherWarning.affected_areas.ilike(search),
            models.WeatherWarning.ai_report.ilike(search),
            models.WeatherWarning.valid_time_start.ilike(search),
            models.WeatherWarning.valid_time_end.ilike(search)
        ))

    if start_dt:
        query = query.filter(models.WeatherWarning.issue_time >= start_dt.strftime("%Y-%m-%d 00:00:00"))
    if end_dt:
        query = query.filter(models.WeatherWarning.issue_time < end_dt.strftime("%Y-%m-%d 00:00:00"))

    warnings = query.order_by(models.WeatherWarning.issue_time.desc()).offset(skip).limit(limit).all()
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

    print(f"[{now_local()}] Manually re-reporting warning: {warning.title}")
    current_time = now_local().strftime("%Y-%m-%d %H:%M:%S")

    system_prompt = """
    你現在是一位專業的氣象主播，負責即時插播氣象特報。
    請根據接收到的氣象局特報資料，撰寫一段廣播稿。
    1. **絕對不要**使用任何寒暄語或開場白。
    2. 開頭直接切入重點。
    3. **清楚區分**「發布時間」與「實際生效時間」；若特報是今天發布、明天生效，必須明確說「明天」或具體時段，不能說成今天整天。
    4. 只要使用相對日期詞，**一定要帶上日期**，例如「今（7）日」、「明（8）日上午」；禁止單獨出現「今天、今日、明天、今晚」等沒有日期的寫法。
    5. 若要描述發布時間，應寫成像「氣象署今（7）日上午發布特報」這樣的格式。
    6. 若提到具體時刻，一律使用台灣口語的「幾點幾分」格式，不要使用「幾時幾分」。
    7. 具體時間中的數字請使用中文數字，例如「九點三十分」、「晚上十一點」。
    8. 強調受影響地區。
    9. 簡潔扼要，約 70-110 字，優先精簡，不要贅述重複資訊。
    """
    
    user_prompt = f"""
    【目前播報時間】
    {current_time}

    【特報資料】
    標題: {warning.title}
    發布時間: {warning.issue_time}
    生效開始時間: {warning.valid_time_start or '未提供'}
    生效結束時間: {warning.valid_time_end or '未提供'}
    更新時間: {warning.update_time or '未提供'}
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
    print(f"[{now_local()}] Checking for new warnings...")
    if not CWA_API_KEY:
        return {"status": "error", "message": "No CWA API Key"}

    # W-C0033-002: 各類特報
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/W-C0033-002?Authorization={CWA_API_KEY}&format=JSON"
    
    new_warnings_count = 0
    
    try:
        async with httpx.AsyncClient() as client:
            data = await fetch_json_with_retry(client, url, timeout=20.0, label="CWA warnings API")
            
            records = data.get("records", {}).get("record", [])
            if not isinstance(records, list):
                records = [records] # 處理單筆可能是 dict 的情況

            for record in records:
                dataset_info = record.get("datasetInfo", {})
                dataset_desc = dataset_info.get("datasetDescription", "未分類特報") # Title
                issue_time = dataset_info.get("issueTime", "")
                valid_time = dataset_info.get("validTime", {})
                valid_time_start = valid_time.get("startTime", "")
                valid_time_end = valid_time.get("endTime", "")
                update_time = dataset_info.get("update", "")
                
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
                current_time = now_local().strftime("%Y-%m-%d %H:%M:%S")
                system_prompt = """
                你現在是一位專業的氣象主播，負責即時插播氣象特報。
                請根據接收到的氣象局特報資料，撰寫一段廣播稿。

                【撰寫要求】
                1. 開頭直接切入重點 (如「氣象署發布...」)。
                2. 口語化改寫：去除公文式標號，但**必須準確描述實際生效時段**。
                3. **清楚區分**「發布時間」與「實際生效時間」；若今天發布、明天生效，必須說成「明天上午至晚上」或對應時段，不能講成今天整天。
                4. 只要使用相對日期詞，**一定要帶上日期**，例如「今（7）日」、「明（8）日上午」；禁止單獨出現「今天、今日、明天、今晚」等沒有日期的寫法。
                5. 若要描述發布時間，應寫成像「氣象署今（7）日上午發布特報」這樣的格式。
                6. 若提到具體時刻，一律使用台灣口語的「幾點幾分」格式，不要使用「幾時幾分」。
                7. 具體時間中的數字請使用中文數字，例如「九點三十分」、「晚上十一點」。
                8. 強調受影響區域：清楚唸出受影響的縣市。
                9. 簡潔扼要：保留危險原因與防範措施，約 70-110 字，優先精簡，不要贅述重複資訊。
                10. 語氣：急切、權威、清晰。
                """
                
                user_prompt = f"""
                【目前播報時間】
                {current_time}

                【特報資料】
                標題: {dataset_desc}
                發布時間: {issue_time}
                生效開始時間: {valid_time_start or '未提供'}
                生效結束時間: {valid_time_end or '未提供'}
                更新時間: {update_time or '未提供'}
                受影響地區: {affected_areas_str}
                內容全文: {content_text}
                """
                
                ai_report = await generate_ai_text(system_prompt, user_prompt)
                
                # 呼叫 TTS
                await send_to_tts_api(ai_report)
                
                # 存入 DB
                try:
                    new_warning = models.WeatherWarning(
                        dataset_id="W-C0033-002",
                        issue_time=issue_time,
                        valid_time_start=valid_time_start,
                        valid_time_end=valid_time_end,
                        update_time=update_time,
                        title=dataset_desc,
                        content=content_text,
                        affected_areas=affected_areas_str,
                        ai_report=ai_report,
                        is_reported=True
                    )
                    db.add(new_warning)
                    db.commit()
                    new_warnings_count += 1
                except IntegrityError:
                    db.rollback()
                    print(f"Duplicate warning record ignored: {dataset_desc} ({issue_time})")
                except Exception as e:
                    db.rollback()
                    print(f"Error saving warning record: {e}")
                
    except Exception as e:
        print(f"Error processing warnings: {repr(e)}")
        return {"status": "error", "message": str(e)}

    return {"status": "success", "new_warnings_processed": new_warnings_count}

# 4. 新增：地震相關 Endpoints

@app.get("/api/earthquakes", response_model=List[EarthquakeRecord])
def get_earthquakes(
    skip: int = 0,
    limit: int = 10,
    q: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.EarthquakeAlert)
    start_dt, end_dt = parse_date_range(start_date, end_date)
    
    if q:
        search = f"%{q}%"
        query = query.filter(or_(
            cast(models.EarthquakeAlert.earthquake_no, String).ilike(search),
            models.EarthquakeAlert.location.ilike(search),
            models.EarthquakeAlert.magnitude.ilike(search),
            models.EarthquakeAlert.content.ilike(search),
            models.EarthquakeAlert.intensity_summary.ilike(search),
            models.EarthquakeAlert.ai_report.ilike(search)
        ))

    if start_dt:
        query = query.filter(models.EarthquakeAlert.origin_time >= start_dt.strftime("%Y-%m-%d 00:00:00"))
    if end_dt:
        query = query.filter(models.EarthquakeAlert.origin_time < end_dt.strftime("%Y-%m-%d 00:00:00"))

    eqs = query.order_by(models.EarthquakeAlert.origin_time.desc()).offset(skip).limit(limit).all()
    return eqs

@app.post("/api/earthquakes/{eq_id}/re-report")
async def re_report_earthquake(eq_id: int, db: Session = Depends(get_db)):
    """
    手動觸發：重新生成 AI 地震報告並播報
    """
    eq = db.query(models.EarthquakeAlert).filter(models.EarthquakeAlert.id == eq_id).first()
    if not eq:
        raise HTTPException(status_code=404, detail="找不到該地震紀錄 ID")

    print(f"[{now_local()}] Manually re-reporting earthquake: {eq.earthquake_no}")

    system_prompt = """
    你現在是一位專業的新聞主播，負責插播即時地震快訊。
    請根據接收到的地震資料，撰寫一段廣播稿。
    
    【撰寫要求】
    1. **語氣緊急且嚴肅**，但保持冷靜。
    2. 開頭直接播報：「氣象署發布顯著有感地震報告...」。
    3. 清楚唸出：發生時間 (轉為口語，如剛才、今天晚間)、震央位置、芮氏規模。
    4. **特別強調**：最大震度達到 3 級以上的縣市，若無則強調「最大震度 x 級」。
    5. 提醒民眾保持冷靜，注意餘震。
    6. 字數約 70-110 字，優先精簡，不要贅述重複資訊。
    """
    
    user_prompt = f"""
    【地震資料】
    編號: {eq.earthquake_no}
    時間: {eq.origin_time}
    規模: {eq.magnitude}
    深度: {eq.depth} 公里
    位置: {eq.location}
    各地震度概要: {eq.intensity_summary}
    氣象署簡述: {eq.content}
    """
    
    ai_report = await generate_ai_text(system_prompt, user_prompt)
    await send_to_tts_api(ai_report)
    
    eq.ai_report = ai_report
    db.commit()
    
    return {"status": "success", "ai_report": ai_report}

@app.post("/api/cron/check-earthquakes")
async def check_and_process_earthquakes(db: Session = Depends(get_db)):
    """
    每分鐘檢查：抓取 CWA E-A0015-001 -> 比對 DB -> 生成報告 -> 播報 -> 存檔
    """
    print(f"[{now_local()}] Checking for earthquakes...")
    if not CWA_API_KEY:
        return {"status": "error", "message": "No CWA API Key"}
        
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-001?Authorization={CWA_API_KEY}&format=JSON"
    
    new_eq_count = 0
    try:
        async with httpx.AsyncClient() as client:
            data = await fetch_json_with_retry(client, url, timeout=20.0, label="CWA earthquakes API")
            
            # CWA 地震資料結構
            records = data.get("records", {}).get("Earthquake", [])
            if not isinstance(records, list): records = [records]

            for item in records:
                eq_no = item.get("EarthquakeNo") # Unique ID
                if not eq_no: continue
                
                # Check DB
                exists = db.query(models.EarthquakeAlert).filter(models.EarthquakeAlert.earthquake_no == eq_no).first()
                if exists:
                    # 假設地震編號相同就是同一筆，不做更新
                    continue
                
                # New Earthquake Found
                print(f"New Earthquake Found: {eq_no}")
                
                report_content = item.get("ReportContent", "")
                eq_info = item.get("EarthquakeInfo", {})
                origin_time = eq_info.get("OriginTime", "")
                focal_depth = str(eq_info.get("FocalDepth", ""))
                
                epicenter = eq_info.get("Epicenter", {})
                location = epicenter.get("Location", "")
                
                magnitude_info = eq_info.get("EarthquakeMagnitude", {})
                magnitude = str(magnitude_info.get("MagnitudeValue", ""))
                
                # 解析震度 (Intensity)
                shaking_areas = item.get("Intensity", {}).get("ShakingArea", [])
                if not isinstance(shaking_areas, list): shaking_areas = [shaking_areas]
                
                # 整理震度資訊 (例如: "宜蘭縣4級, 花蓮縣3級...")
                # 使用 dict 來去重，Key 為縣市名稱，Value 為該縣市最大震度資訊
                county_map = {}

                for area in shaking_areas:
                    raw_county = area.get("CountyName", "")
                    if not raw_county: continue
                    
                    # 清洗縣市名稱 (去除空白)
                    county = raw_county.strip()
                    
                    intensity_str = area.get("AreaIntensity", "").strip()
                    
                    # 解析震度數值 (只取第一個數字)
                    intensity_val = 0
                    try:
                        digits = ''.join(filter(str.isdigit, intensity_str))
                        if digits:
                            intensity_val = int(digits[0])
                    except:
                        pass
                    
                    # 如果該縣市未出現過，或新震度比較大，則更新
                    if county not in county_map or intensity_val > county_map[county]["val"]:
                        county_map[county] = {
                            "county": county,
                            "str": intensity_str,
                            "val": intensity_val
                        }
                
                # 轉回 list 並依照震度大小排序
                sorted_intensities = list(county_map.values())
                sorted_intensities.sort(key=lambda x: x["val"], reverse=True)
                
                # 建構完整清單 (不限制數量，因為使用者想要「所有」區域)
                summary_parts = [f"{item['county']}{item['str']}" for item in sorted_intensities]
                intensity_summary_str = ", ".join(summary_parts)
                
                # Generate AI Report
                system_prompt = """
                你現在是一位專業的新聞主播，負責插播即時地震快訊。
                請根據接收到的地震資料，撰寫一段廣播稿。
                
                【撰寫要求】
                1. **語氣緊急且嚴肅**，但保持冷靜。
                2. 開頭直接播報：「氣象署發布顯著有感地震報告...」。
                3. 清楚唸出：發生時間 (轉為口語，如剛才、今天晚間)、震央位置、芮氏規模。
                4. **特別強調**：最大震度達到 3 級以上的縣市，若無則強調「各地最大震度」。
                5. 提醒民眾保持冷靜，注意餘震。
    6. 字數約 70-110 字，優先精簡，不要贅述重複資訊。
                """
                
                user_prompt = f"""
                【地震資料】
                編號: {eq_no}
                時間: {origin_time}
                規模: {magnitude}
                深度: {focal_depth} 公里
                位置: {location}
                各地震度概要: {intensity_summary_str}
                氣象署簡述: {report_content}
                """
                
                ai_report = await generate_ai_text(system_prompt, user_prompt)
                
                # TTS
                await send_to_tts_api(ai_report)
                
                # Save to DB
                try:
                    new_eq = models.EarthquakeAlert(
                        earthquake_no=eq_no,
                        report_type=item.get("ReportType", "地震報告"),
                        origin_time=origin_time,
                        location=location,
                        magnitude=magnitude,
                        depth=focal_depth,
                        content=report_content,
                        intensity_summary=intensity_summary_str,
                        ai_report=ai_report,
                        is_reported=True
                    )
                    db.add(new_eq)
                    db.commit()
                    new_eq_count += 1
                except IntegrityError:
                    db.rollback()
                    print(f"Duplicate earthquake record ignored: {eq_no}")
                except Exception as e:
                    db.rollback()
                    print(f"Error saving earthquake record {eq_no}: {e}")

    except Exception as e:
        print(f"Error processing earthquakes: {repr(e)}")
        return {"status": "error", "message": str(e)}

    return {"status": "success", "new_earthquakes_processed": new_eq_count}

@app.get("/")
def read_root():
    return {"status": "ok", "service": "Weather Backend"}

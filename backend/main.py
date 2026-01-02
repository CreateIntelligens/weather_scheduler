import os
import json
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# 允許跨域 (雖然 Docker 內我們會用 Proxy，但開發時保留彈性)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 從環境變數讀取 Key (Docker Compose 會傳入)
CWA_API_KEY = os.getenv("CWA_API_KEY") or os.getenv("VITE_CWA_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("VITE_GEMINI_API_KEY")

# AI 設定
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()
AI_MODEL = os.getenv("AI_MODEL", "gemini-1.5-flash")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

TARGET_CITIES = [
    '基隆市', '臺北市', '新北市', '桃園市', '新竹市', '新竹縣', '苗栗縣', '臺中市',
    '彰化縣', '南投縣', '雲林縣', '嘉義市', '嘉義縣', '臺南市', '高雄市', '屏東縣',
    '宜蘭縣', '花蓮縣', '臺東縣', '澎湖縣', '金門縣', '連江縣'
]

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

async def fetch_overview(client: httpx.AsyncClient) -> str:
    """抓取全臺天氣概況"""
    # if not CWA_API_KEY:
    #     return "未設定 CWA API Key"
    
    # url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-A0003-001?Authorization={CWA_API_KEY}&format=JSON"
    # try:
    #     resp = await client.get(url)
    #     resp.raise_for_status()
    #     data = resp.json()
    #     location = data.get("records", {}).get("location", [])
    #     if location:
    #         weather_elem = location[0].get("weatherElement", [])
    #         desc_elem = next((e for e in weather_elem if e["elementName"] == "WeatherDescription"), None)
    #         if desc_elem and desc_elem.get("elementValue"):
    #             return desc_elem["elementValue"][0]["value"]
    # except Exception as e:
    #     print(f"Error fetching overview: {e}")
    # return "暫無概況資料"
    return ""

async def fetch_cities_forecast(client: httpx.AsyncClient) -> List[CityWeather]:
    """抓取各縣市預報"""
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

async def generate_ai_report(client: httpx.AsyncClient, overview: str, cities: List[CityWeather]) -> str:
    """呼叫 AI 生成報告 (支援 Gemini, OpenAI, Groq)"""
    
    cities_summary = "\n".join([
        f"{c.name}: 天氣{c.wx}, 氣溫{c.minT}-{c.maxT}度, 降雨機率{c.pop}%"
        for c in cities
    ])

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

    user_content = f"""
    【輸入資料】:
    [觀測數據]:
    {cities_summary}
    """

    try:
        if AI_PROVIDER == "openai":
            if not OPENAI_API_KEY: return "未設定 OpenAI API Key"
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": AI_MODEL, # e.g., "gpt-3.5-turbo", "gpt-4o"
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ]
            }
            resp = await client.post(url, headers=headers, json=payload, timeout=30.0)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

        elif AI_PROVIDER == "groq":
            if not GROQ_API_KEY: return "未設定 Groq API Key"
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": AI_MODEL, # e.g., "llama3-8b-8192", "mixtral-8x7b-32768"
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ]
            }
            resp = await client.post(url, headers=headers, json=payload, timeout=30.0)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

        else: # Default to Gemini
            if not GEMINI_API_KEY: return "未設定 Gemini Key"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{AI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            
            # Gemini 的 prompt 結構不同
            full_prompt = system_prompt + "\n" + user_content
            
            resp = await client.post(
                url, 
                json={"contents": [{"parts": [{"text": full_prompt}]}]},
                timeout=20.0
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", overview)

    except Exception as e:
        print(f"AI Generation Error ({AI_PROVIDER}): {str(e).split('?key=')[0]}")
        return overview or f"{AI_PROVIDER} 分析暫時無法使用，請參考上方數據。"

from datetime import datetime, timedelta

# ... (Existing imports)

# ... (Existing setup)

# --- Simple In-Memory Cache ---
weather_cache = {
    "data": None,
    "last_updated": None
}

# ... (Existing helper functions: fetch_overview, fetch_cities_forecast, generate_ai_report)

@app.get("/api/weather", response_model=WeatherResponse)
async def get_weather(refresh: bool = False):
    global weather_cache
    
    now = datetime.now()
    
    # 1. 如果沒有強制更新，且快取存在且夠新 (例如 55 分鐘內)，直接回傳快取
    if not refresh and weather_cache["data"] and weather_cache["last_updated"]:
        # 判斷是否過期 (這裡設為 55 分鐘，確保每小時排程更新前，使用者還是能拿到舊的而不是空的)
        if now - weather_cache["last_updated"] < timedelta(minutes=55):
            print("Using cached data")
            return weather_cache["data"]

    print("Fetching fresh data...")
    async with httpx.AsyncClient() as client:
        # 2. 平行抓取概況與城市數據
        overview = await fetch_overview(client)
        cities = await fetch_cities_forecast(client)
        
        # 3. 生成 AI 報告
        ai_report = await generate_ai_report(client, overview, cities)
        
        response_data = WeatherResponse(
            overview=overview,
            cities=cities,
            ai_report=ai_report
        )
        
        # 4. 更新快取
        weather_cache["data"] = response_data
        weather_cache["last_updated"] = now
        
        return response_data


@app.get("/api/weather/{city_name}", response_model=CityWeather)
async def get_city_weather(city_name: str):
    """查詢單一縣市天氣"""
    async with httpx.AsyncClient() as client:
        if not CWA_API_KEY:
             raise HTTPException(status_code=500, detail="未設定 CWA API Key")

        # 注意：CWA API 的 locationName 參數需要完全匹配，例如 "臺北市" 不能寫 "台北市"
        url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001?Authorization={CWA_API_KEY}&format=JSON&locationName={city_name}"
        
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            location = data.get("records", {}).get("location", [])
            
            if not location:
                raise HTTPException(status_code=404, detail=f"找不到縣市: {city_name}，請確認名稱是否正確 (例如: 臺北市)")
            
            loc = location[0]
            weather_elements = loc.get("weatherElement", [])

            def get_val(name):
                el = next((e for e in weather_elements if e["elementName"] == name), None)
                if el and el.get("time") and len(el["time"]) > 0:
                    return el["time"][0]["parameter"]["parameterName"]
                return "-"
            
            return CityWeather(
                name=loc["locationName"],
                wx=get_val("Wx"),
                pop=get_val("PoP"),
                minT=get_val("MinT"),
                maxT=get_val("MaxT")
            )

        except httpx.HTTPStatusError as e:
             raise HTTPException(status_code=e.response.status_code, detail="無法連線至氣象署 API")
        except Exception as e:
             print(f"Error fetching city: {e}")
             raise HTTPException(status_code=500, detail="內部伺服器錯誤")

@app.get("/")
def read_root():
    return {"status": "ok", "service": "Weather Backend"}

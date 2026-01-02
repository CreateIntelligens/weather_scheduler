# AI 氣象整點報馬仔 (Weather AI Assistant)

一個結合中央氣象署資料與大型語言模型 (LLM) 的全方位氣象監控系統。系統會每小時自動更新台灣各縣市天氣預報，並透過 AI 生成專業的分析報告，最後透過 TTS (文字轉語音) 服務進行語音推播。

## 🌟 主要功能

- **全台監控**：涵蓋台灣 22 個縣市的即時天氣預報（天氣、溫差、降雨機率）。
- **AI 氣象員**：支援 **Gemini**, **OpenAI**, 及 **Groq** 多種模型，生成簡潔專業的氣象快訊。
- **自動排程**：內建 Scheduler 每小時整點自動抓取最新資料。
- **高效快取**：採用記憶體快取機制，API 呼叫實現毫秒級回應。
- **TTS 整合**：自動將氣象報告轉發至指定的 TTS API。
- **繁簡轉換**：針對特定 TTS 引擎（如 `indextts`）自動進行繁簡轉換。
- **現代化介面**：提供漂亮且響應式的 React 儀表板。

## 🏗️ 系統架構

- **Frontend**: React + Vite + Tailwind CSS (視覺化看板)
- **Backend API**: FastAPI (提供 API 與資料處理)
- **Scheduler**: Python APScheduler (負責定時任務與 TTS 轉發)
- **Container**: Docker + Docker Compose (一鍵部署)

## 🚀 快速啟動

### 1. 環境設定

在專案根目錄 `.env` 檔案中填入您的 API Keys。
(注意：若您是單獨在 `backend` 資料夾下啟動服務，請確保 `backend/` 目錄下也有一份相同的 `.env` 檔案，或參考 `docker-compose-backend.yaml` 中的路徑設定)

```env
# 中央氣象署 API Key
VITE_CWA_API_KEY=YOUR_CWA_API_KEY
```

### 2. 啟動服務

使用 Docker Compose 一鍵啟動後端與排程服務：

```powershell
docker-compose -f backend/docker-compose-backend.yaml up --build
```

若需啟動前端看板：
```powershell
docker-compose up --build
```

## 接口說明 (API Endpoints)

- **GET `/api/weather`**: 取得全台完整氣象資料與 AI 報告。
- **GET `/api/weather/{city_name}`**: 查詢單一縣市（例如：臺北市）的天氣概況。
- **Swagger UI**: 啟動後存取 `http://localhost:8000/docs` 查看詳細文件。

## 技術細節

- **排程邏輯**：系統在每小時 `00` 分會觸發更新。
- **TTS 轉發**：報告會 POST 到 `http://10.9.0.35:5456/api/stream-speak`。
- **語言處理**：針對 `indextts` 引擎，系統會使用 `OpenCC` 將報告轉換為簡體中文以確保語音合成效果。

# AI 氣象整點報馬仔 (AI Weather & Alert System)

一個結合中央氣象署 (CWA) 開放資料、大型語言模型 (LLM) 與 TTS 語音合成的全方位氣象監控系統。系統能自動監控全台天氣預報、即時氣象特報以及地震快訊，並透過 AI 生成專業的口語化廣播稿進行推播。

## 🌟 核心功能

### 1. 全方位監控
- **🌦️ 整點預報 (Hourly)**：每小時自動抓取全台 22 縣市天氣，生成氣象快訊。
- **⚠️ 氣象特報 (Warnings)**：每 10 分鐘檢查是否有新發布的特報（如豪雨、強風），即時插播。
- **🌋 地震快訊 (Earthquakes)**：每分鐘監控氣象署地震報告，即時播報顯著有感地震，包含震央、規模與各地震度摘要。

### 2. 智慧 AI 氣象員
- 整合 **Gemini**, **OpenAI**, **Groq** 等多種 LLM 模型。
- 自動將生硬的氣象數據轉化為溫暖、專業且適合廣播的口語稿。
- 支援「查看原始資料」，確保資訊準確性。

### 3. 歷史資料庫 (PostgreSQL)
- 完整保存所有歷史預報、特報與地震紀錄。
- 提供 **關鍵字搜尋**、**日期區間篩選** 與 **分頁** 功能，可隨時回顧過往事件。
- 支援 **手動重播**，可隨時針對任一歷史紀錄重新生成 AI 報告並播報。

### 4. 現代化儀表板 (Dashboard)
- **即時看板 (Live)**：一目了然的最新氣象資訊與 AI 報告。
- **歷史紀錄 (History)**：包含三種歷史表格
  - 歷史預報 Broadcast：顯示報告時間、AI 摘要、播報時間
  - 特報紀錄 Warnings：顯示發布時間、受影響地區、AI 報告、播報時間
  - 地震紀錄 Earthquakes：顯示發生時間、規模/位置、AI 報告、播報時間
- **歷史篩選功能**：每張表皆支援關鍵字搜尋與開始/結束日期的小月曆區間篩選
- **系統狀態**：顯示目前連線狀態與使用的 AI 模型。

---

## 🏗️ 系統架構

本專案採用微服務架構，全容器化部署：

- **Frontend**: React + Vite + Tailwind CSS (響應式監控看板)
- **Backend**: FastAPI (高效非同步 API)
- **Database**: PostgreSQL (資料持久化)
- **Scheduler**: Python APScheduler (精準排程控制)
- **Deployment**: Docker Compose

---

## 🚀 快速啟動

### 1. 環境設定

請在專案根目錄建立 `.env` 檔案，並填入以下資訊：

```env
# 中央氣象署 API Key (必填)
VITE_CWA_API_KEY=YOUR_CWA_API_KEY

# Google Gemini API Key (必填，用於生成報告)
VITE_GEMINI_API_KEY=YOUR_GEMINI_API_KEY

# AI 設定 (可選，預設使用 Gemini)
AI_PROVIDER=gemini  # 或 openai, groq
AI_MODEL=gemini-1.5-flash

# OpenAI / Groq Keys (若使用該 Provider 則必填)
OPENAI_API_KEY=
GROQ_API_KEY=

# 資料庫設定
POSTGRES_USER=weather_user
POSTGRES_PASSWORD=change_me
POSTGRES_DB=weather_db
DATABASE_URL=postgresql://weather_user:change_me@db:5432/weather_db

# 內部服務設定
BACKEND_BASE_URL=http://weather-backend:8000
TTS_API_URL=http://127.0.0.1:5456/api/stream-speak
TTS_ENGINE=indextts

# 前端開發伺服器
VITE_PORT=5175
VITE_ALLOWED_HOSTS=
VITE_API_PROXY_TARGET=http://weather-backend:8000
```

### 2. 啟動服務 (三種模式)

我們提供了靈活的啟動方式，您可以依需求選擇：

#### A. 🚀 全端啟動 (推薦)
同時啟動前端、後端、資料庫與排程器。
```bash
docker-compose up --build -d
```
- **前端看板**: http://localhost:5175
- **後端 API**: http://localhost:8000/docs

#### B. 🔧 只啟動後端
若您只需要 API 與資料庫，不需要前端介面。
```bash
cd backend
docker-compose -f docker-compose-backend.yaml up --build -d
```

#### C. 🎨 只啟動前端
```bash
docker-compose -f docker-compose-frontend.yaml up --build -d
```

### 3. 歷史紀錄頁目前支援

- 三種資料表各自獨立查詢，不會互相影響搜尋條件與分頁
- 關鍵字搜尋
  - 預報：可搜尋 AI 摘要、概況、城市資料
  - 特報：可搜尋標題、內容、受影響地區、AI 報告
  - 地震：可搜尋編號、規模、位置、震度摘要、AI 報告
- 日期區間篩選
  - 預報依 `report_time`
  - 特報依 `issue_time`
  - 地震依 `origin_time`
- 每筆特報 / 地震紀錄皆可手動「重播」

---

## 📅 排程與優先順序

系統內建精密排程，當多種事件同時觸發時，優先順序如下：

1.  **🔴 地震快訊** (每分鐘檢查) - 最緊急，優先處理。
2.  **🟠 氣象特報** (每 10 分鐘檢查) - 次要緊急。
3.  **🟢 整點預報** (每小時整點) - 例行性廣播。

---

## 🛠️ 開發與維護

### 清空/重置資料庫
若需要清空所有歷史紀錄，請執行：
```bash
docker-compose down
docker volume rm weather_test_postgres_data
docker-compose up -d
```

### 查看系統 Logs
```bash
docker-compose logs -f
```
(您可以在 Logs 中看到完整的 AI 生成過程與排程觸發紀錄)

---

## 🔗 相關資源
- [中央氣象署開放資料平臺](https://opendata.cwa.gov.tw/)
- [Google AI Studio (Gemini API)](https://aistudio.google.com/)

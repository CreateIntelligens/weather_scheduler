import React, { useState, useEffect, useRef } from 'react';
import { CloudSun, RefreshCw, Clock, MapPin, Thermometer, Umbrella, Info, AlertCircle, WifiOff, Sparkles, Bot, Send, History } from 'lucide-react';

// 從環境變數讀取 API Keys
// Vite 專案中，環境變數需以 VITE_ 開頭
const CWA_API_KEY = import.meta.env.VITE_CWA_API_KEY || "";
const GEMINI_API_KEY = import.meta.env.VITE_GEMINI_API_KEY || "";

const TARGET_CITIES = ['臺北市', '新北市', '臺中市', '臺南市', '高雄市', '花蓮縣'];

export default function App() {
  const [messages, setMessages] = useState([]);
  const [cityData, setCityData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isGeneratingAI, setIsGeneratingAI] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [nextUpdateTime, setNextUpdateTime] = useState(null);
  const [countdown, setCountdown] = useState('');
  const [error, setError] = useState(null);
  const [usingProxy, setUsingProxy] = useState(false);
  
  const timerRef = useRef(null);
  const chatEndRef = useRef(null);

  const formatTime = (date) => {
    return date ? date.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '--:--:--';
  };

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isGeneratingAI]);

  // --- 1. 通用 Fetch 函式 (含 Proxy) ---
  const fetchWithFallback = async (url) => {
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Direct Error ${res.status}`);
      return await res.json();
    } catch (directErr) {
      console.warn("直接連線失敗，嘗試 Proxy...", directErr);
      try {
        setUsingProxy(true);
        const proxyUrl = `https://api.allorigins.win/raw?url=${encodeURIComponent(url)}&disableCache=${new Date().getTime()}`;
        const res = await fetch(proxyUrl);
        if (!res.ok) throw new Error(`Proxy Error ${res.status}`);
        return await res.json();
      } catch (proxyErr) {
        throw new Error(`無法存取氣象署資料 (${directErr.message})`);
      }
    }
  };

  // --- 2. Gemini AI 生成函式 ---
  const generateWeatherReport = async (overviewText, citiesData) => {
    if (!GEMINI_API_KEY) {
        return overviewText || "未設定 Gemini API Key，無法進行 AI 分析。";
    }

    setIsGeneratingAI(true);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 20000);

    try {
      const citiesSummary = citiesData.map(c => 
        `${c.name}: 天氣${c.wx}, 氣溫${c.minT}-${c.maxT}度, 降雨機率${c.pop}%`
      ).join('\n');

      const prompt = `
        你現在是一位專業且精準的氣象分析師。請根據以下資料撰寫最新的整點氣象快訊。
        
        【嚴格要求】:
        1. **絕對不要**使用任何寒暄語或開場白。
        2. **直接切入**天氣重點。
        3. 語氣要像即時通訊軟體中的「重點整理」一樣，簡潔有力但保有專業度。
        4. 請根據數據分析目前是受什麼天氣系統（如東北季風、鋒面）影響。
        5. 針對接下來 1-3 小時做簡單的穿著或攜帶雨具建議。
        6. 字數約 100-150 字。

        【輸入資料】:
        [官方概況]: ${overviewText || "無文字概況，請依據數據分析"}
        [觀測數據]:
        ${citiesSummary}
      `;

      const response = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key=${GEMINI_API_KEY}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            contents: [{ parts: [{ text: prompt }] }]
          }),
          signal: controller.signal
        }
      );
      
      clearTimeout(timeoutId);
      const data = await response.json();
      const generatedText = data.candidates?.[0]?.content?.parts?.[0]?.text;
      
      return generatedText || overviewText || "目前無法取得 AI 分析報告，請參考詳細數據。";

    } catch (e) {
      console.error("Gemini Generation Error:", e);
      return overviewText || "連線逾時或錯誤，無法取得 AI 分析，請直接參考右側數據。";
    } finally {
      setIsGeneratingAI(false);
    }
  };

  // --- 3. 主流程 ---
  const fetchWeatherData = async () => {
    setLoading(true);
    setError(null);
    
    const currentTimestamp = new Date();

    try {
      // 檢查 CWA Key
      if (!CWA_API_KEY) throw new Error("未設定氣象署 API Key");

      // A. 抓取全臺天氣概況
      const overviewUrl = `https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-A0003-001?Authorization=${CWA_API_KEY}&format=JSON`;
      let overviewRawText = "";
      try {
        const overviewJson = await fetchWithFallback(overviewUrl);
        if (overviewJson.records?.location?.[0]?.weatherElement) {
          const el = overviewJson.records.location[0].weatherElement.find(e => e.elementName === "WeatherDescription");
          if (el) overviewRawText = el.elementValue[0].value;
        }
      } catch (e) {
        console.warn("概況資料 fallback", e);
      }

      // B. 抓取各縣市預報
      const locations = encodeURIComponent(TARGET_CITIES.join(','));
      const forecastUrl = `https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001?Authorization=${CWA_API_KEY}&format=JSON&locationName=${locations}`;
      const forecastJson = await fetchWithFallback(forecastUrl);

      let processedCities = [];
      if (forecastJson.records?.location) {
        processedCities = forecastJson.records.location.map(loc => {
          const weatherElements = loc.weatherElement;
          const getValue = (name) => {
             const el = weatherElements.find(e => e.elementName === name);
             return el && el.time && el.time[0] ? el.time[0].parameter.parameterName : '-';
          };
          return {
            name: loc.locationName,
            wx: getValue('Wx'),
            pop: getValue('PoP'),
            minT: getValue('MinT'),
            maxT: getValue('MaxT')
          };
        });
        setCityData(processedCities);
      }
      
      setLoading(false);

      // C. 呼叫 AI 生成報告
      const reportText = await generateWeatherReport(overviewRawText, processedCities);
      
      setMessages(prev => [
        ...prev,
        {
          id: Date.now(),
          time: currentTimestamp,
          text: reportText,
          sender: 'AI'
        }
      ]);

      setLastUpdated(currentTimestamp);
      calculateNextHour(currentTimestamp);

    } catch (err) {
      console.error("Fetch流程錯誤:", err);
      setError(err.message);
      setLoading(false);
      
      setMessages(prev => [
        ...prev,
        {
          id: Date.now(),
          time: new Date(),
          text: `系統錯誤：${err.message}`,
          sender: 'System',
          isError: true
        }
      ]);
    }
  };

  const calculateNextHour = (now) => {
    const nextHour = new Date(now);
    nextHour.setHours(now.getHours() + 1);
    nextHour.setMinutes(0);
    nextHour.setSeconds(0);
    nextHour.setMilliseconds(0);
    setNextUpdateTime(nextHour);

    const diff = nextHour.getTime() - now.getTime();
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(fetchWeatherData, diff);
  };

  useEffect(() => {
    const interval = setInterval(() => {
      if (nextUpdateTime) {
        const now = new Date();
        const diff = nextUpdateTime - now;
        if (diff > 0) {
          const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
          const seconds = Math.floor((diff % (1000 * 60)) / 1000);
          setCountdown(`${minutes}分${seconds}秒`);
        } else {
          setCountdown("更新中...");
        }
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [nextUpdateTime]);

  useEffect(() => {
    fetchWeatherData();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return (
    <div className="h-screen bg-gradient-to-br from-indigo-50 to-blue-100 text-slate-800 font-sans p-2 md:p-6 flex flex-col overflow-hidden">
      
      {/* Header */}
      <header className="flex-none bg-white/90 backdrop-blur-md rounded-xl p-4 shadow-sm flex flex-wrap justify-between items-center gap-4 border border-white/50 mb-4">
        <div className="flex items-center gap-3">
          <div className="bg-indigo-600 p-2 rounded-lg text-white shadow-indigo-200 shadow-md">
            <Bot size={24} />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-800 tracking-tight">AI 氣象整點報馬仔</h1>
            <p className="text-xs text-slate-500">資料來源: 中央氣象署 (CWA)</p>
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs font-medium text-slate-600">
           <div className="bg-slate-100 px-3 py-1.5 rounded-full flex items-center gap-2">
             <History size={14} />
             <span>上次: {formatTime(lastUpdated)}</span>
           </div>
           <div className="bg-green-100 text-green-700 px-3 py-1.5 rounded-full flex items-center gap-2 border border-green-200">
             <Clock size={14} />
             <span>下個整點: {countdown || '--:--'}</span>
           </div>
           {usingProxy && (
             <div className="bg-orange-100 text-orange-700 px-2 py-1 rounded text-[10px]">Proxy</div>
           )}
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex flex-col lg:flex-row gap-4 overflow-hidden min-h-0">
        
        {/* Chat Window */}
        <div className="flex-[2] bg-white rounded-2xl shadow-md border border-slate-200 flex flex-col overflow-hidden relative">
          <div className="p-3 bg-slate-50 border-b border-slate-100 flex items-center gap-2 text-sm text-slate-500">
            <Sparkles size={16} className="text-indigo-500" />
            <span>即時氣象推播頻道</span>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-6 bg-slate-50/30 scroll-smooth">
            {messages.length === 0 && !isGeneratingAI && !loading && (
              <div className="text-center text-slate-400 py-10">
                尚無訊息，等待第一次更新...
              </div>
            )}

            {messages.map((msg) => (
              <div key={msg.id} className={`flex gap-3 ${msg.sender === 'System' ? 'justify-center' : 'justify-start'}`}>
                {msg.sender === 'AI' && (
                  <div className="flex-none w-8 h-8 bg-gradient-to-tr from-indigo-500 to-purple-500 rounded-full flex items-center justify-center text-white shadow-sm mt-1">
                    <Bot size={16} />
                  </div>
                )}
                
                <div className={`flex flex-col max-w-[85%] ${msg.sender === 'System' ? 'items-center w-full' : 'items-start'}`}>
                  {msg.sender !== 'System' && (
                    <span className="text-[10px] text-slate-400 mb-1 ml-1">
                      {msg.sender} • {formatTime(msg.time)}
                    </span>
                  )}
                  
                  <div className={`
                    rounded-2xl px-5 py-3 text-sm leading-relaxed shadow-sm
                    ${msg.isError 
                      ? 'bg-red-50 text-red-600 border border-red-100'
                      : msg.sender === 'System' 
                        ? 'bg-slate-200 text-slate-600 text-xs py-1 px-3 rounded-full'
                        : 'bg-white border border-slate-100 text-slate-700 rounded-tl-none'}
                  `}>
                    {msg.text.split("\n").map((line, i) => (
                      <p key={i} className={line.trim() === '' ? 'h-2' : 'mb-1 last:mb-0'}>{line}</p>
                    ))}
                  </div>
                </div>
              </div>
            ))}

            {isGeneratingAI && (
               <div className="flex gap-3">
                 <div className="flex-none w-8 h-8 bg-slate-200 rounded-full flex items-center justify-center mt-1">
                   <Bot size={16} className="text-slate-500" />
                 </div>
                 <div className="flex flex-col items-start">
                   <span className="text-[10px] text-slate-400 mb-1 ml-1">AI 助理</span>
                   <div className="bg-white border border-slate-100 rounded-2xl rounded-tl-none px-4 py-3 shadow-sm">
                     <div className="flex gap-1">
                       <span className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce"></span>
                       <span className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce delay-75"></span>
                       <span className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce delay-150"></span>
                     </div>
                   </div>
                 </div>
               </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <div className="p-3 bg-white border-t border-slate-100 flex gap-2">
             <button 
               onClick={fetchWeatherData} 
               disabled={isGeneratingAI || loading}
               className="w-full bg-slate-100 hover:bg-slate-200 text-slate-600 py-2 px-4 rounded-lg text-sm flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
             >
               <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
               {loading ? "資料更新中..." : "手動立即更新氣象"}
             </button>
          </div>
        </div>

        {/* Right: Live Status */}
        <div className="flex-1 lg:max-w-sm bg-white rounded-2xl shadow-md border border-slate-200 flex flex-col overflow-hidden h-full">
           <div className="p-4 border-b border-slate-100 bg-slate-50">
             <h3 className="font-bold text-slate-700 flex items-center gap-2">
               <MapPin size={18} className="text-red-500" /> 
               即時觀測看板
             </h3>
           </div>
           
           <div className="overflow-y-auto p-4 space-y-3 flex-1 bg-slate-50/30">
              {loading && cityData.length === 0 ? (
                [1,2,3,4,5].map(i => (
                  <div key={i} className="h-20 bg-white rounded-xl animate-pulse border border-slate-100"></div>
                ))
              ) : (
                cityData.map((city) => (
                  <div key={city.name} className="bg-white p-3 rounded-xl shadow-sm border border-slate-100 flex items-center justify-between group hover:border-indigo-200 transition-colors">
                    <div>
                      <span className="text-base font-bold text-slate-800">{city.name}</span>
                      <p className="text-xs text-slate-500 mt-1 flex items-center gap-1">
                         {city.wx}
                      </p>
                    </div>
                    <div className="text-right">
                      <div className="flex items-center justify-end gap-1 text-slate-700 font-bold text-sm">
                        <Thermometer size={14} className="text-orange-500" />
                        <span>{city.minT}°-{city.maxT}°</span>
                      </div>
                      <div className="flex items-center justify-end gap-1 text-blue-500 text-xs mt-1">
                        <Umbrella size={12} />
                        <span>降雨 {city.pop}%</span>
                      </div>
                    </div>
                  </div>
                ))
              )}
           </div>
        </div>

      </div>
    </div>
  );
}

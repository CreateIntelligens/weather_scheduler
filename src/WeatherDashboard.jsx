import React, { useState, useEffect } from 'react';
import { CloudSun, RefreshCw, Clock, MapPin, Thermometer, Umbrella, Bot, AlertTriangle, Activity, Database, FileText, X, Search, ChevronLeft, ChevronRight } from 'lucide-react';

// 使用 Vite Proxy (在 vite.config.js 設定轉發 /api -> weather-backend:8000)
// 這樣瀏覽器只需要訪問 5175，不需要直接連 8000
const BACKEND_URL = '';
const TABLE_CELL = 'px-5 py-4 align-top';
const TABLE_TIME_CELL = `${TABLE_CELL} text-xs text-slate-400 whitespace-nowrap tabular-nums`;
const TABLE_ID_CELL = `${TABLE_CELL} w-20 whitespace-nowrap font-mono text-xs text-slate-400`;
const TABLE_ACTION_CELL = `${TABLE_CELL} w-24 whitespace-nowrap`;

export default function App() {
  const [activeTab, setActiveTab] = useState('live'); // live, db
  const [currentWeather, setCurrentWeather] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dbData, setDbData] = useState({ forecasts: [], warnings: [], earthquakes: [] });
  const [dbLoading, setDbLoading] = useState(false);
  const [systemConfig, setSystemConfig] = useState({ ai_provider: '', ai_model: 'Loading...' });

  // Pagination & Search State
  const [page, setPage] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const LIMIT = 10;

  // Modal State
  const [modalOpen, setModalOpen] = useState(false);
  const [modalContent, setModalContent] = useState('');
  const [modalOriginal, setModalOriginal] = useState('');
  const [modalTitle, setModalTitle] = useState('');

  const openModal = (title, aiContent, originalContent) => {
    setModalTitle(title);
    setModalContent(aiContent);
    setModalOriginal(originalContent);
    setModalOpen(true);
  };

  // Fetch Config
  const fetchConfig = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/config`);
      const data = await res.json();
      setSystemConfig(data);
    } catch (e) {
      console.error("Fetch config error:", e);
    }
  };

  // Live Weather Fetch (Default: Get from DB)
  const fetchLiveWeather = async (forceRefresh = false) => {
    setLoading(true);
    try {
      // If forceRefresh is false, backend returns the latest from DB
      // Add timestamp to prevent browser caching
      const url = forceRefresh 
        ? `${BACKEND_URL}/api/weather?refresh=true&t=${Date.now()}` 
        : `${BACKEND_URL}/api/weather?t=${Date.now()}`;
        
      const res = await fetch(url); 
      const data = await res.json();
      setCurrentWeather(data);
    } catch (e) {
      console.error("Fetch live weather error:", e);
    } finally {
      setLoading(false);
    }
  };

  // Manual Broadcast (Generates new AI report and speaks)
  const handleBroadcast = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/weather/broadcast`, { method: 'POST' });
      const data = await res.json();
      // Update UI with the new report
      fetchLiveWeather(false); 
      alert("已觸發手動播報！");
    } catch (e) {
      console.error("Broadcast error:", e);
      alert("播報觸發失敗");
    } finally {
      setLoading(false);
    }
  };

  // DB Data Fetch
  const fetchDbData = async () => {
    setDbLoading(true);
    const skip = page * LIMIT;
    const q = searchQuery ? `&q=${encodeURIComponent(searchQuery)}` : '';
    
    try {
      const [forecastsRes, warningsRes, eqsRes] = await Promise.all([
        fetch(`${BACKEND_URL}/api/forecasts?limit=${LIMIT}&skip=${skip}${q}`),
        fetch(`${BACKEND_URL}/api/warnings?limit=${LIMIT}&skip=${skip}${q}`),
        fetch(`${BACKEND_URL}/api/earthquakes?limit=${LIMIT}&skip=${skip}${q}`)
      ]);

      const forecasts = await forecastsRes.json();
      const warnings = await warningsRes.json();
      const earthquakes = await eqsRes.json();

      setDbData({ forecasts, warnings, earthquakes });
    } catch (e) {
      console.error("Fetch DB data error:", e);
    } finally {
      setDbLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
    fetchLiveWeather();
  }, []);

  useEffect(() => {
    if (activeTab === 'db') {
      fetchDbData();
    }
  }, [activeTab, page]); // Re-fetch when tab or page changes

  // Trigger search when enter key is pressed or search button clicked
  const handleSearch = () => {
    setPage(0); // Reset to first page on new search
    fetchDbData();
  };

  const TabButton = ({ id, label, icon: Icon }) => (
    <button
      onClick={() => setActiveTab(id)}
      className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
        activeTab === id 
        ? 'bg-indigo-600 text-white shadow-md' 
        : 'bg-white text-slate-600 hover:bg-slate-100'
      }`}
    >
      <Icon size={18} />
      {label}
    </button>
  );

  return (
    <div className="min-h-screen bg-slate-100 text-slate-800 font-sans p-4 md:p-8">
      
      {/* Header */}
      <header className="mb-8 flex flex-col md:flex-row justify-between items-center gap-4">
        <div className="flex items-center gap-3">
          <div className="bg-gradient-to-tr from-indigo-500 to-purple-500 p-3 rounded-xl text-white shadow-lg">
            <Bot size={28} />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-800">AI 氣象/特報/地震 監控中心</h1>
          </div>
        </div>

        <div className="flex bg-white p-1 rounded-xl shadow-sm border border-slate-200">
          <TabButton id="live" label="即時看板" icon={Activity} />
          <TabButton id="db" label="歷史紀錄 (DB)" icon={Database} />
        </div>
      </header>

      {/* Main Content */}
      <main>
        {activeTab === 'live' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            
            {/* Left: AI Report & Controls */}
            <div className="lg:col-span-2 space-y-6">
              
              {/* AI Report Card */}
              <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
                <div className="flex justify-between items-center mb-4">
                  <h2 className="text-lg font-bold flex items-center gap-2">
                    <Bot className="text-indigo-500" />
                    最新 AI 氣象快訊
                  </h2>
                  <div className="flex gap-2">
                    <button 
                      onClick={() => fetchLiveWeather(false)}
                      className="flex items-center gap-1 bg-slate-100 hover:bg-slate-200 px-3 py-1.5 rounded-lg text-sm transition-colors"
                    >
                      <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
                      重新整理 (從 DB)
                    </button>
                    <button 
                      onClick={handleBroadcast}
                      className="flex items-center gap-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 px-3 py-1.5 rounded-lg text-sm transition-colors border border-indigo-200"
                    >
                      <FileText size={14} />
                      生成並播報 (AI)
                    </button>
                  </div>
                </div>

                <div className="bg-slate-50 rounded-xl p-5 border border-slate-100 min-h-[200px] leading-relaxed whitespace-pre-line text-slate-700">
                  {loading ? (
                    <div className="flex items-center justify-center h-full text-slate-400 gap-2">
                      <RefreshCw className="animate-spin" />
                      載入中...
                    </div>
                  ) : currentWeather?.ai_report ? (
                    currentWeather.ai_report
                  ) : (
                    <span className="text-slate-400">尚無資料，請嘗試更新。</span>
                  )}
                </div>
              </div>

              {/* City Forecasts Grid */}
              <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
                 <h3 className="font-bold text-slate-700 mb-4 flex items-center gap-2">
                   <MapPin className="text-red-500" /> 全臺主要縣市預報
                 </h3>
                 <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                    {loading ? (
                      [...Array(6)].map((_, i) => <div key={i} className="h-24 bg-slate-50 animate-pulse rounded-xl"></div>)
                    ) : (
                      currentWeather?.cities?.map(city => (
                        <div key={city.name} className="bg-slate-50 p-3 rounded-xl border border-slate-100 hover:border-indigo-200 transition-all">
                          <div className="font-bold text-slate-800">{city.name}</div>
                          <div className="text-xs text-slate-500 mt-1">{city.wx}</div>
                          <div className="flex justify-between items-end mt-2">
                            <span className="text-sm font-bold text-orange-500">{city.minT}-{city.maxT}°C</span>
                            <span className="text-xs text-blue-500 bg-blue-50 px-1.5 py-0.5 rounded">☂ {city.pop}%</span>
                          </div>
                        </div>
                      ))
                    )}
                 </div>
              </div>
            </div>

            {/* Right: Quick Stats or Status */}
            <div className="space-y-6">
               <div className="bg-gradient-to-br from-blue-500 to-indigo-600 rounded-2xl p-6 text-white shadow-lg">
                 <h3 className="font-bold text-white/90 mb-2">系統狀態</h3>
                 <div className="space-y-4">
                   <div className="flex justify-between items-center bg-white/10 p-3 rounded-lg backdrop-blur-sm">
                     <span className="text-sm text-white/80">API 連線</span>
                     <span className="text-xs bg-green-400/20 text-green-300 px-2 py-1 rounded">正常</span>
                   </div>
                   <div className="flex justify-between items-center bg-white/10 p-3 rounded-lg backdrop-blur-sm">
                     <span className="text-sm text-white/80">AI 模組</span>
                     <span className="text-xs bg-green-400/20 text-green-300 px-2 py-1 rounded">
                       {systemConfig.ai_model}
                     </span>
                   </div>
                   <div className="text-xs text-white/60 text-center pt-2">
                     最後更新: {new Date().toLocaleTimeString()}
                   </div>
                 </div>
               </div>
            </div>

          </div>
        )}

        {activeTab === 'db' && (
          <div className="space-y-10">
            {/* 1. Forecast History */}
            <DataTable 
              title="歷史預報 Broadcast (每日 09:00 / 12:00 / 20:00 更新)" 
              icon={CloudSun}
              iconColor="text-blue-500"
              apiUrl="/api/forecasts"
              columnClasses={['w-20', 'w-48', 'min-w-[28rem]', 'w-48']}
              renderRow={(f) => (
                <tr key={f.id} className="hover:bg-slate-50/80">
                  <td className={TABLE_ID_CELL}>#{f.id}</td>
                  <td className={TABLE_TIME_CELL}>
                    {new Date(f.report_time).toLocaleString()}
                  </td>
                  <td 
                    className={`${TABLE_CELL} max-w-xl truncate text-sm leading-6 text-slate-600 cursor-pointer hover:text-indigo-600 hover:underline decoration-dotted`}
                    onClick={() => openModal(`天氣預報 #${f.id}`, f.ai_report, f.overview)}
                    title="點擊查看完整報告"
                  >
                    {f.ai_report || "無 AI 報告"}
                  </td>
                  <td className={`${TABLE_TIME_CELL} text-right`}>
                    {new Date(f.created_at).toLocaleString()}
                  </td>
                </tr>
              )}
              headers={['ID', '報告時間', 'AI 摘要 (前 50 字)', '播報時間']}
            />

            {/* 2. Warnings History */}
            <DataTable 
              title="特報紀錄 Warnings (每10分鐘更新)" 
              icon={AlertTriangle}
              iconColor="text-orange-500"
              apiUrl="/api/warnings"
              columnClasses={['w-20', 'w-64', 'w-56', 'w-48', 'w-64', 'min-w-[22rem]', 'w-48', 'w-24']}
              renderRow={(w) => (
                <tr key={w.id} className="hover:bg-slate-50/80">
                  <td className={TABLE_ID_CELL}>#{w.id}</td>
                  <td className={`${TABLE_CELL} text-sm font-semibold text-orange-600 leading-6`}>{w.title}</td>
                  <td className={TABLE_TIME_CELL}>
                    {w.valid_time_start && w.valid_time_end
                      ? `${new Date(w.valid_time_start).toLocaleString()} - ${new Date(w.valid_time_end).toLocaleString()}`
                      : '--'}
                  </td>
                  <td className={TABLE_TIME_CELL}>{new Date(w.issue_time).toLocaleString()}</td>
                  <td className={`${TABLE_CELL} max-w-sm truncate text-sm leading-6 text-slate-600`} title={w.affected_areas}>
                    {w.affected_areas}
                  </td>
                  <td 
                    className={`${TABLE_CELL} max-w-lg truncate text-sm leading-6 text-slate-500 cursor-pointer hover:text-indigo-600 hover:underline decoration-dotted`}
                    onClick={() => openModal(`特報: ${w.title}`, w.ai_report, w.content)}
                    title="點擊查看完整報告"
                  >
                    {w.ai_report || "尚未生成"}
                  </td>
                  <td className={TABLE_TIME_CELL}>
                    {new Date(w.created_at).toLocaleString()}
                  </td>
                  <td className={TABLE_ACTION_CELL}>
                     <button 
                       onClick={async () => {
                         if(confirm('確定要重新生成並播報此特報嗎？')) {
                           await fetch(`${BACKEND_URL}/api/warnings/${w.id}/re-report`, {method: 'POST'});
                           alert("已送出重播請求，請稍後點擊整理按鈕。");
                         }
                       }}
                       className="text-indigo-600 hover:text-indigo-800 text-xs font-medium border border-indigo-200 px-2.5 py-1.5 rounded-md bg-white"
                     >
                       重播
                     </button>
                  </td>
                </tr>
              )}
              headers={['ID', '標題', '生效期間', '發布時間', '受影響地區', 'AI 報告', '播報時間', '操作']}
            />

            {/* 3. Earthquakes History */}
            <DataTable 
              title="地震紀錄 Earthquakes (每分鐘更新)" 
              icon={Activity}
              iconColor="text-red-500"
              apiUrl="/api/earthquakes"
              columnClasses={['w-24', 'w-48', 'w-64', 'min-w-[22rem]', 'w-48', 'w-24']}
              renderRow={(eq) => (
                <tr key={eq.id} className="hover:bg-slate-50/80">
                  <td className={TABLE_ID_CELL}>#{eq.earthquake_no}</td>
                  <td className={TABLE_TIME_CELL}>{new Date(eq.origin_time).toLocaleString()}</td>
                  <td className={TABLE_CELL}>
                    <div className="font-bold text-red-600">M {eq.magnitude}</div>
                    <div className="text-xs leading-5 text-slate-500 mt-1">{eq.location}</div>
                  </td>
                  <td 
                    className={`${TABLE_CELL} max-w-lg truncate text-sm leading-6 text-slate-500 cursor-pointer hover:text-indigo-600 hover:underline decoration-dotted`}
                    onClick={() => openModal(`地震報告 #${eq.earthquake_no}`, eq.ai_report, `【氣象署簡述】:\n${eq.content}\n\n【各縣市震度摘要】:\n${eq.intensity_summary}`)}
                    title="點擊查看完整報告"
                  >
                    {eq.ai_report || "尚未生成"}
                  </td>
                  <td className={TABLE_TIME_CELL}>
                    {new Date(eq.created_at).toLocaleString()}
                  </td>
                  <td className={TABLE_ACTION_CELL}>
                     <button 
                       onClick={async () => {
                         if(confirm('確定要重新生成並播報此地震資訊嗎？')) {
                           await fetch(`${BACKEND_URL}/api/earthquakes/${eq.id}/re-report`, {method: 'POST'});
                           alert("已送出重播請求，請稍後點擊整理按鈕。");
                         }
                       }}
                       className="text-indigo-600 hover:text-indigo-800 text-xs font-medium border border-indigo-200 px-2.5 py-1.5 rounded-md bg-white"
                     >
                       重播
                     </button>
                  </td>
                </tr>
              )}
              headers={['編號', '發生時間', '規模/位置', 'AI 報告', '播報時間', '操作']}
            />

          </div>
        )}
      </main>

      {/* Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" onClick={() => setModalOpen(false)}>
          <div className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="p-4 border-b border-slate-100 flex justify-between items-center bg-slate-50">
              <h3 className="font-bold text-slate-700 flex items-center gap-2">
                <FileText className="text-indigo-500" size={20} />
                {modalTitle}
              </h3>
              <button onClick={() => setModalOpen(false)} className="text-slate-400 hover:text-slate-600 transition-colors">
                <X size={24} />
              </button>
            </div>
            <div className="p-6 overflow-y-auto max-h-[70vh] space-y-6">
              {/* AI Section */}
              <div className="space-y-2">
                <h4 className="text-xs font-bold text-indigo-500 uppercase tracking-wider flex items-center gap-1">
                  <Bot size={14} /> AI 廣播分析
                </h4>
                <div className="bg-indigo-50/50 rounded-xl p-4 text-slate-700 leading-relaxed whitespace-pre-line border border-indigo-100">
                  {modalContent || <span className="text-slate-400 italic">無 AI 內容</span>}
                </div>
              </div>

              {/* Original Content Section */}
              <div className="space-y-2">
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1">
                  <Database size={14} /> 氣象署原始資料
                </h4>
                <div className="bg-slate-50 rounded-xl p-4 text-slate-600 text-sm leading-relaxed whitespace-pre-line border border-slate-100 font-mono">
                  {modalOriginal || <span className="text-slate-400 italic">無原始觀測資料</span>}
                </div>
              </div>
            </div>
            <div className="p-4 border-t border-slate-100 bg-slate-50 flex justify-end">
              <button 
                onClick={() => setModalOpen(false)}
                className="px-4 py-2 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg transition-colors font-medium text-sm"
              >
                關閉
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Reusable DataTable Component
function DataTable({ title, icon: Icon, iconColor, apiUrl, renderRow, headers, columnClasses = [] }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const LIMIT = 10;

  const fetchData = async (
    nextPage = page,
    nextSearchQuery = searchQuery,
    nextStartDate = startDate,
    nextEndDate = endDate
  ) => {
    setLoading(true);
    const skip = nextPage * LIMIT;
    const q = nextSearchQuery ? `&q=${encodeURIComponent(nextSearchQuery)}` : '';
    const start = nextStartDate ? `&start_date=${encodeURIComponent(nextStartDate)}` : '';
    const end = nextEndDate ? `&end_date=${encodeURIComponent(nextEndDate)}` : '';
    const cacheBuster = `&t=${Date.now()}`;
    
    try {
      // Use the global BACKEND_URL
      const res = await fetch(`${BACKEND_URL}${apiUrl}?limit=${LIMIT}&skip=${skip}${q}${start}${end}${cacheBuster}`);
      const json = await res.json();
      setData(json);
    } catch (e) {
      console.error(`Error fetching ${title}:`, e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData(page, searchQuery, startDate, endDate);
  }, [page]); // Re-fetch on page change

  const handleSearch = () => {
    const nextPage = 0;
    setPage(nextPage);
    fetchData(nextPage, searchQuery, startDate, endDate);
  };

  const handleClearFilters = () => {
    const nextPage = 0;
    setSearchQuery('');
    setStartDate('');
    setEndDate('');
    setPage(nextPage);
    fetchData(nextPage, '', '', '');
  };

  return (
    <section>
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-4">
        <h3 className="text-xl font-bold text-slate-700 flex items-center gap-2">
          <Icon className={iconColor} /> {title}
        </h3>
        
        <div className="flex flex-col md:flex-row gap-2 w-full md:w-auto md:items-center">
          <div className="relative flex-1 md:w-72">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
            <input 
              type="text"
              placeholder="搜尋關鍵字，例如 臺北、強風、6.1"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              className="w-full pl-9 pr-4 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
              aria-label="開始日期"
            />
            <span className="text-xs text-slate-400">到</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
              aria-label="結束日期"
            />
          </div>
          <button 
             onClick={handleSearch}
             className="bg-slate-100 hover:bg-slate-200 text-slate-600 px-3 py-1.5 rounded-lg text-sm transition-colors"
           >
             搜尋
           </button>
          <button 
             onClick={handleClearFilters}
             className="bg-white hover:bg-slate-50 text-slate-500 px-3 py-1.5 rounded-lg text-sm transition-colors border border-slate-200"
           >
             清除
           </button>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        {/* Table Content */}
        <div className="overflow-x-auto min-h-[150px]">
          {loading ? (
             <div className="flex items-center justify-center py-10 text-slate-400 gap-2">
               <RefreshCw className="animate-spin" /> 載入中...
             </div>
          ) : data.length === 0 ? (
             <div className="text-center py-10 text-slate-400">
               無資料
             </div>
          ) : (
            <table className="min-w-full text-left border-separate border-spacing-0">
              <colgroup>
                {headers.map((_, i) => <col key={i} className={columnClasses[i] || ''} />)}
              </colgroup>
              <thead className="bg-slate-50 text-slate-500 border-b border-slate-200">
                <tr>
                  {headers.map((h, i) => <th key={i} className="px-5 py-3.5 text-xs font-semibold tracking-wide whitespace-nowrap">{h}</th>)}
                </tr>
              </thead>
              <tbody className="text-sm divide-y divide-slate-100">
                {data.map(item => renderRow(item))}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer / Pagination */}
        <div className="bg-slate-50 border-t border-slate-200 p-3 flex justify-between items-center">
           <button 
             onClick={fetchData} 
             className="flex items-center gap-1 text-slate-500 hover:text-indigo-600 text-xs font-medium transition-colors"
           >
             <RefreshCw size={12} /> 重新整理列表
           </button>

           <div className="flex items-center gap-2">
             <button 
               onClick={() => setPage(p => Math.max(0, p - 1))}
               disabled={page === 0 || loading}
               className="p-1.5 border border-slate-200 rounded-md hover:bg-white disabled:opacity-50"
             >
               <ChevronLeft size={16} />
             </button>
             <span className="text-xs font-medium text-slate-600">
               第 {page + 1} 頁
             </span>
             <button 
               onClick={() => setPage(p => p + 1)}
               disabled={loading || data.length < LIMIT} // Disable if fetched less than limit (likely end)
               className="p-1.5 border border-slate-200 rounded-md hover:bg-white disabled:opacity-50"
             >
               <ChevronRight size={16} />
             </button>
           </div>
        </div>
      </div>
    </section>
  );
}

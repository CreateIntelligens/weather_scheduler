from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from database import Base

class WeatherWarning(Base):
    __tablename__ = "weather_warnings"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(String, index=True) # e.g., W-C0033-002
    issue_time = Column(String, index=True) # 來自 API 的 issueTime 字串，用來判斷唯一性
    title = Column(String) # datasetDescription, e.g., 陸上強風特報
    content = Column(Text) # contentText
    affected_areas = Column(Text) # JSON string or comma-separated list of locations
    
    ai_report = Column(Text, nullable=True) # 儲存 AI 生成的廣播稿
    is_reported = Column(Boolean, default=False) # 是否已播報過
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class EarthquakeAlert(Base):
    __tablename__ = "earthquake_alerts"

    id = Column(Integer, primary_key=True, index=True)
    earthquake_no = Column(Integer, unique=True, index=True) # e.g. 115003
    report_type = Column(String) # e.g. "地震報告"
    origin_time = Column(String) # e.g. "2026-01-12 21:31:49"
    location = Column(String) # e.g. "宜蘭縣政府東方 24.9 公里"
    magnitude = Column(String) # e.g. "5.3"
    depth = Column(String) # e.g. "70.3"
    content = Column(Text) # The full ReportContent text
    
    # Store simplified intensity info, e.g. "宜蘭縣3級, 桃園市3級"
    intensity_summary = Column(Text, nullable=True)
    
    ai_report = Column(Text, nullable=True)
    is_reported = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class WeatherForecast(Base):
    __tablename__ = "weather_forecasts"

    id = Column(Integer, primary_key=True, index=True)
    report_time = Column(DateTime(timezone=True), server_default=func.now()) # 呼叫 API 的時間
    
    overview = Column(Text, nullable=True) # 全台概況
    
    # Store detailed city data as JSON string for simplicity, or we could create a separate table.
    # For now, let's store a summary string or JSON.
    cities_data = Column(Text) # JSON string of city data
    
    ai_report = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())



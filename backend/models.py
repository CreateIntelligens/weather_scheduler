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

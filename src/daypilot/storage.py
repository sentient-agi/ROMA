from __future__ import annotations
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

Base = declarative_base()

class TaskRow(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True, nullable=False)
    title = Column(String, nullable=False)
    start = Column(DateTime, nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    reminder_offset_minutes = Column(Integer, nullable=False, default=10)
    ring_call = Column(Boolean, nullable=False, default=False)
    timezone = Column(String, nullable=False, default="Africa/Lagos")
    rrule = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="scheduled")

def get_session(db_url: str = "sqlite:///daypilot.db"):
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()

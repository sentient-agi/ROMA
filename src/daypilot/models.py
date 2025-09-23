from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class Task(BaseModel):
    title: str
    start: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    reminder_offset_minutes: int = 10
    ring_call: bool = False
    rrule: Optional[str] = None
    notes: Optional[str] = None

class DayPlan(BaseModel):
    user_id: Optional[int] = None
    timezone: str = "Africa/Lagos"
    tasks: List[Task] = Field(default_factory=list)

class PlanResult(BaseModel):
    pretty_plan: str
    scheduled_jobs: int
    ics_path: Optional[str] = None

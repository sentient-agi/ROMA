from __future__ import annotations
from pydantic import BaseModel, Field
from .agent import plan_and_schedule



class DayPilotInput(BaseModel):
    narration: str = Field(..., description="Natural language plan.")
    timezone: str = Field("Africa/Lagos")
    telegram_user_id: int | None = Field(None, description="If set, reminders DM this Telegram user.")

class DayPilotOutput(BaseModel):
    pretty_plan: str
    scheduled_jobs: int
    ics_path: str | None = None

class DayPilotExecutor:
    async def execute(self, input: DayPilotInput) -> DayPilotOutput:
        res = plan_and_schedule(
            input.narration,
            timezone=input.timezone,
            telegram_user_id=input.telegram_user_id
        )
        return DayPilotOutput(
            pretty_plan=res.pretty_plan,
            scheduled_jobs=res.scheduled_jobs,
            ics_path=res.ics_path
        )

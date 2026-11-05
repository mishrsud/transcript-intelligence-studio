from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class InsightError(Exception):
    def __init__(self, code: str, message: str, status: int = 502):
        super().__init__(message)
        self.code, self.status = code, status


class InsightRequest(BaseModel):
    provider: Literal['openai', 'anthropic', 'openrouter', 'compatible']
    model: str = Field(min_length=1, max_length=200, pattern=r'^[A-Za-z0-9][A-Za-z0-9._:/@-]*$')
    base_url: str | None = Field(default=None, max_length=2048)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class KeyInsight(StrictModel):
    text: str = Field(min_length=1, max_length=1500)
    segment_index: int = Field(ge=0)


class ActionItem(StrictModel):
    action: str = Field(min_length=1, max_length=1500)
    owner: str | None
    due_date: str | None
    segment_index: int = Field(ge=0)


class InsightOutput(StrictModel):
    summary: str = Field(min_length=1, max_length=4000)
    key_insights: list[KeyInsight] = Field(max_length=20)
    action_items: list[ActionItem] = Field(max_length=30)

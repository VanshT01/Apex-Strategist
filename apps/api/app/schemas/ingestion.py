from pydantic import BaseModel, Field


class IngestionRequest(BaseModel):
    year: int = Field(ge=2018, le=2100, examples=[2024])
    event: str | int = Field(examples=["British Grand Prix"])
    force: bool = False


class IngestionResponse(BaseModel):
    session_id: int
    status: str
    message: str

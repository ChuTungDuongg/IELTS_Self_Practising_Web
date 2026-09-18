from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    server_time: datetime


class ValidationIssue(BaseModel):
    path: str
    message: str


class ValidationResult(BaseModel):
    valid: bool
    errors: list[ValidationIssue]

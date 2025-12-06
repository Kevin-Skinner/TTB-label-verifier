"""
Response schemas for label verification API.
"""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class FieldCheck(BaseModel):
    """Model representing a field verification check."""
    field: str
    form_value: Any
    label_value: Any
    result: str  # "pass", "fail", "review"
    notes: Optional[str] = None

class VerifyResponse(BaseModel):
    """Response model for label verification."""
    status: str  # "pass", "fail", "review"
    field_checks: List[FieldCheck] = []


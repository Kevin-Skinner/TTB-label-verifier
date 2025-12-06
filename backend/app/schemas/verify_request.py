"""
Request schemas for label verification API.
"""
from pydantic import BaseModel
from typing import Optional

class VerifyRequest(BaseModel):
    """Request model for label verification."""
    image_url: Optional[str] = None
    image_base64: Optional[str] = None
    engine_mode: Optional[str] = None


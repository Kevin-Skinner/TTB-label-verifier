"""
Data models for extracted label information.
"""
from pydantic import BaseModel
from typing import Optional, List

class ExtractedLabel(BaseModel):
    """Model representing extracted label data."""
    text_content: Optional[str] = None
    alcohol_content: Optional[float] = None
    volume: Optional[str] = None
    brand_name: Optional[str] = None
    producer_name: Optional[str] = None
    required_elements: List[str] = []
    detected_elements: List[str] = []


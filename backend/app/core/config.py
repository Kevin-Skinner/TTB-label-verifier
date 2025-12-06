"""
Configuration settings for the TTB Label Verifier application.
"""
import os
from typing import Optional

class Settings:
    """Application settings."""
    
    # Engine mode: "local" or "multimodal_llm"
    ENGINE_MODE: str = os.getenv("ENGINE_MODE", "local")
    
    # API Keys
    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    
    # Application settings
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"

settings = Settings()


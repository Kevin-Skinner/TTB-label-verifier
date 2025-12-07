"""
Configuration settings for the TTB Label Verifier application.
"""
import os

class Settings:
    """Application settings."""
    
    # Application settings
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"

settings = Settings()


"""
Base interface for label verification engines.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any

class LabelAnalysisEngine(ABC):
    """Base class for label analysis engines."""
    
    @abstractmethod
    async def analyze(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Analyze a label image and extract data.
        
        Args:
            image_bytes: Raw image bytes
            
        Returns:
            Dictionary containing analysis results with keys:
            - raw_text: Extracted text from the image
            - extracted: Dictionary of extracted fields
            - confidence: Dictionary of confidence scores
        """
        pass


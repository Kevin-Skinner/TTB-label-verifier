"""
Self-test routes for OCR functionality.
"""
import os
from fastapi import APIRouter
from ..services.selftest import run_ocr_selftest

router = APIRouter()


@router.get("/ocr")
async def ocr_selftest():
    """
    Run OCR self-test and return summary.
    
    Uses SELFTEST_BASE_URL environment variable if set to make HTTP requests
    to the running Docker container. If not set, uses TestClient for in-process testing.
    """
    base_url = os.getenv("SELFTEST_BASE_URL")
    summary = run_ocr_selftest(base_url=base_url)
    return summary


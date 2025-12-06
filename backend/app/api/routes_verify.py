from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from ..schemas.verify_response import VerifyResponse, FieldCheck
from ..services.label_engine.ocr_local import get_label_engine
import re
import logging
from typing import Optional, Tuple

router = APIRouter()
logger = logging.getLogger(__name__)

# Constants
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB in bytes
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}

def normalize_string(value: str) -> str:
    """Normalize string for comparison: lowercase and strip whitespace."""
    return value.strip().lower() if value else ""

def compare_strings(form_value: str, label_value: Optional[str]) -> Tuple[str, Optional[str]]:
    """
    Compare two strings (case-insensitive, whitespace-stripped).
    Returns (result, notes) where result is "pass", "fail", or "review".
    """
    if label_value is None:
        return ("review", "Not detected")
    
    form_norm = normalize_string(str(form_value))
    label_norm = normalize_string(str(label_value))
    
    if form_norm == label_norm:
        return ("pass", None)
    else:
        return ("fail", None)

def compare_abv(form_value: float, label_value: Optional[float]) -> Tuple[str, Optional[str]]:
    """
    Compare ABV values with 0.5 tolerance.
    Returns (result, notes) where result is "pass", "fail", or "review".
    """
    if label_value is None:
        return ("review", "Not detected")
    
    try:
        form_abv = float(form_value)
        label_abv = float(label_value)
        
        if abs(form_abv - label_abv) <= 0.5:
            return ("pass", None)
        else:
            return ("fail", None)
    except (ValueError, TypeError):
        return ("review", "Could not parse ABV value")

def normalize_net_contents(value: str) -> Optional[int]:
    """
    Extract numeric value from net contents string.
    Handles formats like "750ml", "750 ml", "750", etc.
    Returns the integer value or None if not found.
    """
    if not value:
        return None
    
    # Extract first sequence of digits
    match = re.search(r'\d+', str(value))
    if match:
        return int(match.group())
    return None

def compare_net_contents(form_value: str, label_value: Optional[str]) -> Tuple[str, Optional[str]]:
    """
    Compare net contents by normalizing to integer values.
    Returns (result, notes) where result is "pass", "fail", or "review".
    """
    if label_value is None:
        return ("review", "Not detected")
    
    form_num = normalize_net_contents(str(form_value))
    label_num = normalize_net_contents(str(label_value))
    
    if form_num is None or label_num is None:
        return ("review", "Could not extract numeric value")
    
    if form_num == label_num:
        return ("pass", None)
    else:
        return ("fail", None)

def compare_boolean(form_value: bool, label_value: Optional[bool]) -> Tuple[str, Optional[str]]:
    """
    Compare boolean values.
    Returns (result, notes) where result is "pass", "fail", or "review".
    """
    if label_value is None:
        return ("review", "Not detected")
    
    if form_value == bool(label_value):
        return ("pass", None)
    else:
        return ("fail", None)

@router.post("/verify", response_model=VerifyResponse)
async def verify_label(
    brand: str = Form(...),
    class_type: str = Form(...),
    abv: float = Form(...),
    net_contents: str = Form(...),
    warning_claimed: bool = Form(...),
    image: UploadFile = File(...)
):
    """
    Verify a TTB label against regulations.
    Accepts multipart/form-data with form fields and an image file.
    """
    # Validation: Check if image file is provided
    if not image or image.filename == "":
        raise HTTPException(status_code=400, detail="Image file is required")
    
    # Validation: Check content type
    if image.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported image type; please upload a JPEG or PNG"
        )
    
    # Read image bytes for size validation
    image_bytes = await image.read()
    
    # Validation: Check file size
    if len(image_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail="Image file too large (max 5 MB)"
        )
    
    # Validation: Check if file is empty
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Image file is required")
    
    # Wrap main logic in try/except for error handling
    try:
        # Get the appropriate engine instance
        engine = get_label_engine()
        
        # Analyze the image using the engine
        engine_output = await engine.analyze(image_bytes)
        
        # Log confidence for debugging (not exposed in API response)
        logger.debug("Label engine confidence: %s", engine_output.get("confidence"))
        
        # Extract the structured data for comparison
        extracted = engine_output.get("extracted", {})
        
        # Compare each field
        field_checks = []
        
        # Brand comparison
        brand_result, brand_notes = compare_strings(brand, extracted.get("brand"))
        field_checks.append(FieldCheck(
            field="brand",
            form_value=brand,
            label_value=extracted.get("brand"),
            result=brand_result,
            notes=brand_notes
        ))
        
        # Class type comparison
        class_result, class_notes = compare_strings(class_type, extracted.get("class_type"))
        field_checks.append(FieldCheck(
            field="class_type",
            form_value=class_type,
            label_value=extracted.get("class_type"),
            result=class_result,
            notes=class_notes
        ))
        
        # ABV comparison
        abv_result, abv_notes = compare_abv(abv, extracted.get("abv"))
        field_checks.append(FieldCheck(
            field="abv",
            form_value=abv,
            label_value=extracted.get("abv"),
            result=abv_result,
            notes=abv_notes
        ))
        
        # Net contents comparison
        net_contents_result, net_contents_notes = compare_net_contents(
            net_contents, extracted.get("net_contents")
        )
        field_checks.append(FieldCheck(
            field="net_contents",
            form_value=net_contents,
            label_value=extracted.get("net_contents"),
            result=net_contents_result,
            notes=net_contents_notes
        ))
        
        # Warning comparison
        warning_result, warning_notes = compare_boolean(
            warning_claimed, extracted.get("warning_present")
        )
        field_checks.append(FieldCheck(
            field="warning",
            form_value=warning_claimed,
            label_value=extracted.get("warning_present"),
            result=warning_result,
            notes=warning_notes
        ))
        
        # Determine overall status based on mandatory fields
        mandatory_fields = ["brand", "class_type", "abv", "net_contents"]
        mandatory_checks = [fc for fc in field_checks if fc.field in mandatory_fields]
        
        # Check if any mandatory field has "fail"
        has_fail = any(fc.result == "fail" for fc in mandatory_checks)
        # Check if all mandatory fields have "pass"
        all_pass = all(fc.result == "pass" for fc in mandatory_checks)
        
        if has_fail:
            overall_status = "fail"
        elif all_pass:
            overall_status = "pass"
        else:
            overall_status = "review"
        
        return VerifyResponse(
            status=overall_status,
            field_checks=field_checks
        )
    
    except HTTPException:
        # Re-raise HTTP exceptions (validation errors)
        raise
    except Exception as e:
        # Log unexpected errors and return generic 500 error
        logger.error(f"Unexpected error during label verification: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal error while analyzing the label"
        )


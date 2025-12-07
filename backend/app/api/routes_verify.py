from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from ..schemas.verify_response import VerifyResponse, FieldCheck
from ..services.label_engine.ocr_local import get_label_engine
import re
import logging
import difflib
import json
from typing import Optional, Tuple, Union
from PIL import Image
import numpy as np
import io

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

def compare_brand(form_value: str, label_value: Optional[str], raw_text: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Compare brand names with enhanced matching logic.
    If initial match fails, checks:
    1. Character count equality
    2. 75% substring match
    3. Form submission appears elsewhere in label
    
    Returns (result, notes, matched_value) where:
    - result is "pass", "fail", or "review"
    - notes is optional explanation
    - matched_value is the matched string from label if all conditions met, otherwise None
    """
    if label_value is None:
        return ("review", "Not detected", None)
    
    form_norm = normalize_string(str(form_value))
    label_norm = normalize_string(str(label_value))
    
    # Exact match - pass
    if form_norm == label_norm:
        return ("pass", None, label_value)
    
    # No match - check enhanced conditions
    form_str = str(form_value).strip()
    label_str = str(label_value).strip()
    
    # Condition 1: 75% substring match (check similarity first)
    # Calculate similarity ratio
    similarity = difflib.SequenceMatcher(None, form_norm, label_norm).ratio()
    if similarity < 0.75:
        return ("fail", None, None)
    
    # Condition 2: Character count equality (case-insensitive, ignoring spaces and punctuation)
    # Normalize by removing both whitespace and punctuation for character count comparison
    form_chars = len(re.sub(r'[\s\W]', '', form_str.lower()))
    label_chars = len(re.sub(r'[\s\W]', '', label_str.lower()))
    
    if form_chars != label_chars:
        return ("fail", None, None)
    
    # Condition 3: Form submission appears elsewhere in label
    raw_text_lower = raw_text.lower()
    form_lower = form_str.lower()
    form_norm_no_spaces = form_norm.replace(" ", "")
    
    # Check if form submission appears in raw text (try multiple variations)
    form_in_text = (
        form_lower in raw_text_lower or 
        form_norm in raw_text_lower or
        form_norm_no_spaces in raw_text_lower
    )
    
    if not form_in_text:
        return ("fail", None, None)
    
    # All 3 conditions met - find the actual matching string in the label
    # Since form submission appears in label (condition 3), extract it from raw_text
    matched_string = None
    
    # Search for form submission in raw text (case-insensitive search, but preserve original case)
    # Try to find the exact phrase matching the form submission
    idx = raw_text_lower.find(form_lower)
    if idx >= 0:
        # Extract the exact matching phrase from original text preserving case
        # Get the length of the form submission to extract the exact phrase
        matched_string = raw_text[idx:idx + len(form_str)].strip()
    
    # If exact phrase not found, try normalized version (without spaces)
    if not matched_string:
        idx = raw_text_lower.find(form_norm)
        if idx >= 0:
            matched_string = raw_text[idx:idx + len(form_norm)].strip()
    
    # If still not found, try normalized version without spaces
    if not matched_string:
        idx = raw_text_lower.find(form_norm_no_spaces)
        if idx >= 0:
            # For no-spaces version, try to extract with word boundaries
            start_idx = max(0, raw_text_lower.rfind(" ", 0, idx) + 1)
            end_idx = raw_text_lower.find(" ", idx + len(form_norm_no_spaces))
            if end_idx == -1:
                end_idx = len(raw_text)
            matched_string = raw_text[start_idx:end_idx].strip()
    
    # If still not found, use label_value since it passed all validation checks
    if not matched_string:
        matched_string = label_value
    
    return ("pass", "Matched with enhanced validation", matched_string)

def compare_abv(form_value: Union[float, str], label_value: Optional[float]) -> Tuple[str, Optional[str]]:
    """
    Compare ABV values with 0.5 tolerance.
    Handles cases where form_value is "n/a" (case-insensitive).
    Returns (result, notes) where result is "pass", "fail", or "review".
    """
    # Check if form_value is "n/a" (case-insensitive)
    form_str = str(form_value).strip().lower()
    if form_str == "n/a":
        if label_value is None:
            return ("pass", "Not detected")
        else:
            return ("review", "User claimed N/A but value detected")
    
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
    Handles cases where form_value is "n/a" (case-insensitive).
    Returns (result, notes) where result is "pass", "fail", or "review".
    """
    # Check if form_value is "n/a" (case-insensitive)
    form_str = normalize_string(str(form_value))
    if form_str == "n/a":
        if label_value is None:
            return ("pass", "Not detected")
        else:
            return ("review", "User claimed N/A but value detected")
    
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
    For warning field: if OCR detects no warning but user claims warning, review (OCR may have missed it).
    If both OCR and user agree (both True or both False), pass.
    """
    if label_value is None:
        return ("review", "Not detected")
    
    # If OCR says no warning (False) but user claims warning (True), review
    # OCR may have missed the warning, so don't automatically fail the user
    if label_value is False and form_value is True:
        return ("review", "Warning claimed but not detected by OCR - manual verification recommended")
    
    # If both agree (both True or both False), pass
    if form_value == bool(label_value):
        return ("pass", None)
    else:
        # OCR says warning (True) but user says no warning (False)
        return ("fail", None)

@router.post("/verify", response_model=VerifyResponse)
async def verify_label(
    brand: str = Form(...),
    class_type: str = Form(...),
    abv: str = Form(...),
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
        raw_text = engine_output.get("raw_text", "")
        confidence = engine_output.get("confidence", {})
        image_size = engine_output.get("image_size")
        field_boxes = engine_output.get("field_boxes")
        
        # Check confidence gate: if relevant_avg_conf < 0.60, return review for all fields
        relevant_avg_conf = confidence.get("relevant_avg_conf", confidence.get("avg_conf", 0.0))
        
        if relevant_avg_conf < 0.60:
            # Build field_checks with result "review" for all five fields
            field_checks = []
            for field_name in ["brand", "class_type", "abv", "net_contents", "warning"]:
                field_value = None
                if field_name == "brand":
                    field_value = brand
                elif field_name == "class_type":
                    field_value = class_type
                elif field_name == "abv":
                    field_value = abv
                elif field_name == "net_contents":
                    field_value = net_contents
                elif field_name == "warning":
                    field_value = warning_claimed
                
                field_checks.append(FieldCheck(
                    field=field_name,
                    form_value=field_value,
                    label_value=None,
                    result="review",
                    notes="Unable to verify with given image. Please check image quality."
                ))
            
            return VerifyResponse(
                status="review",
                field_checks=field_checks,
                image_size=image_size,
                field_boxes=field_boxes
            )
        
        # Compare each field
        field_checks = []
        
        # Brand comparison with enhanced matching logic
        brand_result, brand_notes, matched_brand = compare_brand(
            brand, extracted.get("brand"), raw_text
        )
        # Use matched_brand if found, otherwise use extracted brand
        final_brand_value = matched_brand if matched_brand else extracted.get("brand")
        field_checks.append(FieldCheck(
            field="brand",
            form_value=brand,
            label_value=final_brand_value,
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
        # Convert abv string to float if it's not "n/a", otherwise pass as-is
        abv_value = abv if abv.strip().lower() == "n/a" else float(abv)
        abv_result, abv_notes = compare_abv(abv_value, extracted.get("abv"))
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
        mandatory_fields = ["brand", "class_type", "abv", "net_contents", "warning"]
        mandatory_checks = [fc for fc in field_checks if fc.field in mandatory_fields]
        
        # Special check: If warning is not present (unchecked in form or not detected by OCR), fail
        warning_check = next((fc for fc in mandatory_checks if fc.field == "warning"), None)
        if warning_check:
            # Warning is missing if form says False OR label says False/None
            warning_missing = (
                warning_check.form_value is False or 
                warning_check.label_value is False or 
                warning_check.label_value is None
            )
            if warning_missing:
                overall_status = "fail"
                # Update the warning check to have fail result and note
                warning_check.result = "fail"
                warning_check.notes = "Labels must have warning"
            else:
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
        else:
            # Fallback if warning check not found (shouldn't happen, but handle gracefully)
            has_fail = any(fc.result == "fail" for fc in mandatory_checks)
            all_pass = all(fc.result == "pass" for fc in mandatory_checks)
            
            if has_fail:
                overall_status = "fail"
            elif all_pass:
                overall_status = "pass"
            else:
                overall_status = "review"
        
        return VerifyResponse(
            status=overall_status,
            field_checks=field_checks,
            image_size=image_size,
            field_boxes=field_boxes
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


@router.post("/verify/adjust_field")
async def adjust_field(
    field: str = Form(...),
    box: str = Form(...),
    image: UploadFile = File(...)
):
    """
    Re-OCR a specific region of the image for a given field.
    
    Args:
        field: Field name ("brand", "abv", "net_contents", "warning")
        box: JSON string of bbox [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        image: The image file
        
    Returns:
        JSON with field, text, box, success
    """
    # Validate field
    valid_fields = ["brand", "abv", "net_contents", "warning"]
    if field not in valid_fields:
        raise HTTPException(status_code=400, detail=f"Invalid field. Must be one of: {valid_fields}")
    
    # Parse and validate box
    try:
        bbox = json.loads(box)
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise ValueError("Box must be a list of 4 points")
        for point in bbox:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError("Each point must be [x, y]")
            if not all(isinstance(coord, (int, float)) for coord in point):
                raise ValueError("Coordinates must be numbers")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in box parameter")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid box format: {str(e)}")
    
    # Read image
    try:
        image_bytes = await image.read()
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_width, img_height = img.size
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read image: {str(e)}")
    
    # Compute tight rectangular ROI from bbox
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    left = max(0, int(min(xs)))
    right = min(img_width, int(max(xs)))
    top = max(0, int(min(ys)))
    bottom = min(img_height, int(max(ys)))
    
    # Validate crop region
    if right <= left or bottom <= top:
        raise HTTPException(status_code=400, detail="Invalid box: width or height is zero or negative")
    
    # Crop the region
    try:
        cropped = img.crop((left, top, right, bottom))
        cropped_np = np.array(cropped)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to crop image: {str(e)}")
    
    # Run OCR on the crop
    try:
        engine = get_label_engine()
        # Use the engine's OCR directly - we need to access the underlying OCR
        from ..services.label_engine.ocr_local import get_paddle_ocr
        
        ocr = get_paddle_ocr()
        raw_result = ocr.ocr(cropped_np)
        
        # Extract text from OCR result (similar to PaddleOCREngine logic)
        texts = []
        confidences = []
        
        if raw_result and len(raw_result) > 0:
            res = raw_result[0]
            if isinstance(res, dict) and "rec_texts" in res:
                texts = res.get("rec_texts", [])
                confidences = res.get("rec_scores", [])
            else:
                # Legacy format
                for line in (res if isinstance(res, list) else raw_result):
                    if isinstance(line, (list, tuple)) and len(line) >= 2:
                        if isinstance(line[1], tuple):
                            text, score = line[1]
                        elif len(line) >= 3:
                            text, score = line[1], line[2]
                        else:
                            continue
                        texts.append(str(text))
                        confidences.append(float(score))
        
        # Choose highest confidence text
        if not texts:
            return {
                "field": field,
                "text": None,
                "box": bbox,
                "success": False
            }
        
        # Find best text by confidence
        best_idx = 0
        best_conf = confidences[0] if confidences else 0.0
        for i, conf in enumerate(confidences):
            if conf > best_conf:
                best_conf = conf
                best_idx = i
        
        extracted_text = texts[best_idx].strip()
        
        # Apply field-specific normalization
        if field == "brand":
            # Just trim for brand
            extracted_text = extracted_text.strip()
        elif field == "abv":
            # Extract ABV value
            from ..services.label_engine.ocr_local import extract_abv
            abv_value = extract_abv(extracted_text)
            extracted_text = str(abv_value) if abv_value is not None else extracted_text
        elif field == "net_contents":
            # Extract net contents
            from ..services.label_engine.ocr_local import extract_net_contents
            net_value = extract_net_contents(extracted_text)
            extracted_text = net_value if net_value else extracted_text
        elif field == "warning":
            # For warning, just check if warning-like text
            extracted_text = extracted_text.strip()
        
        return {
            "field": field,
            "text": extracted_text,
            "box": bbox,
            "success": True
        }
        
    except Exception as e:
        logger.error(f"Error during OCR adjustment: {str(e)}", exc_info=True)
        return {
            "field": field,
            "text": None,
            "box": bbox,
            "success": False
        }


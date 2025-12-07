"""
Self-test service for OCR functionality.
Provides a programmatic way to run OCR tests outside of pytest.
"""
import csv
from pathlib import Path
from typing import Dict, List, Any, Optional
import httpx
# Import TestClient explicitly to avoid conflicts with httpx.Client
from fastapi.testclient import TestClient as FastAPITestClient


def get_field_check(field_checks: List[Dict[str, Any]], field_name: str) -> Dict[str, Any] | None:
    """Helper to locate a field check by field name."""
    for check in field_checks:
        if check.get("field") == field_name:
            return check
    return None


def compare_brand(csv_brand: str, label_value: Any) -> bool:
    """Compare brand values case-insensitively with trimmed whitespace."""
    if label_value is None:
        return False
    csv_normalized = csv_brand.strip().lower()
    label_normalized = str(label_value).strip().lower()
    return csv_normalized == label_normalized


def compare_class_type(csv_class_type: str, label_value: Any) -> bool:
    """Compare class_type with exact match."""
    if label_value is None:
        return False
    return str(csv_class_type).strip() == str(label_value).strip()


def compare_abv(csv_abv: str, label_value: Any) -> bool:
    """Compare ABV values."""
    if csv_abv.upper() == "N/A":
        # If CSV says N/A, label_value should be None or empty
        return label_value is None or str(label_value).strip() == ""
    
    if label_value is None:
        return False
    
    try:
        csv_float = float(csv_abv)
        # label_value might be float, int, or string representation
        label_float = float(label_value)
        # Use relative tolerance 1e-2
        return abs(csv_float - label_float) < max(abs(csv_float) * 1e-2, 0.01)
    except (ValueError, TypeError):
        return False


def compare_net_contents(csv_net_contents: str, label_value: Any) -> bool:
    """Compare net contents values."""
    if csv_net_contents.upper() == "N/A":
        # If CSV says N/A, label_value should be None or empty
        return label_value is None or str(label_value).strip() == ""
    
    if label_value is None:
        return False
    
    # Normalize: lowercase and strip spaces
    csv_normalized = str(csv_net_contents).lower().strip().replace(" ", "")
    label_normalized = str(label_value).lower().strip().replace(" ", "")
    return csv_normalized == label_normalized


def compare_warning(csv_warning: str, label_value: Any) -> bool:
    """Compare warning values."""
    csv_bool = csv_warning.lower() == "true"
    # label_value might be boolean or string "true"/"false"
    if label_value is None:
        return False
    label_bool = bool(label_value) if isinstance(label_value, bool) else str(label_value).lower() == "true"
    return csv_bool == label_bool


def _make_verify_request(base_url: Optional[str], files: Dict, data: Dict) -> tuple[int, Dict]:
    """
    Make a POST request to /api/verify endpoint.
    
    Args:
        base_url: Base URL for HTTP requests (None or empty string for TestClient mode)
        files: Files dictionary for multipart form data
        data: Form data dictionary
    
    Returns:
        Tuple of (status_code, response_json)
    """
    if base_url and base_url.strip():
        # HTTP mode: make actual HTTP request using httpx.Client
        url = f"{base_url.rstrip('/')}/api/verify"
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, files=files, data=data)
            return response.status_code, response.json()
    else:
        # TestClient mode: in-process testing using FastAPI's TestClient
        client = _get_test_client()
        response = client.post("/api/verify", files=files, data=data)
        return response.status_code, response.json()


def _get_test_client():
    """Get a test client, creating it lazily to avoid circular imports."""
    from ..main import app
    # Use FastAPITestClient explicitly to avoid confusion with httpx.Client
    return FastAPITestClient(app)


def run_ocr_selftest(base_url: Optional[str] = None) -> Dict[str, Any]:
    """
    Run OCR self-test using CSV test cases.
    
    Args:
        base_url: Optional base URL for HTTP requests (e.g., "http://localhost:8000").
                  If None, uses TestClient for in-process testing.
    
    Returns:
        Summary dict with test results.
    """
    # Load CSV from backend/tests/form_submissions.csv
    csv_path = Path(__file__).parent.parent.parent / "tests" / "form_submissions.csv"
    
    if not csv_path.exists():
        return {
            "total_cases": 0,
            "passed": 0,
            "failed": 0,
            "error": f"CSV file not found: {csv_path}",
            "cases": []
        }
    
    cases = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cases.append(row)
    
    results = []
    passed_count = 0
    failed_count = 0
    
    for case in cases:
        case_result = {
            "image": case["image"],
            "passed": True,
            "failed_fields": []
        }
        
        try:
            # Build image path
            images_dir = csv_path.parent / "images"
            image_path = images_dir / case["image"]
            
            if not image_path.exists():
                case_result["passed"] = False
                case_result["failed_fields"] = ["image file not found"]
                results.append(case_result)
                failed_count += 1
                continue
            
            # Read image bytes
            with open(image_path, "rb") as f:
                image_bytes = f.read()
            
            # Determine content type based on file extension
            content_type = "image/jpeg"
            if image_path.suffix.lower() in [".png"]:
                content_type = "image/png"
            
            # Build form data
            abv_value = "n/a" if case["abv"].upper() == "N/A" else case["abv"]
            # Handle net_contents: if CSV has "N/A", send "n/a", otherwise combine net_contents and volume_unit
            if case["net_contents"].upper() == "N/A":
                net_contents_value = "n/a"
            else:
                # Combine net_contents and volume_unit (e.g., "750" + "mL" -> "750 ml")
                volume_unit_lower = case["volume_unit"].lower()
                net_contents_value = f"{case['net_contents']} {volume_unit_lower}"
            warning_claimed = "true" if case["warning_present"].lower() == "true" else "false"
            
            # Make POST request
            files = {
                "image": (case["image"], image_bytes, content_type)
            }
            data = {
                "brand": case["brand"],
                "class_type": case["class_type"],
                "abv": abv_value,
                "net_contents": net_contents_value,
                "warning_claimed": warning_claimed,
            }
            
            status_code, result_json = _make_verify_request(base_url, files, data)
            
            if status_code != 200:
                case_result["passed"] = False
                case_result["failed_fields"] = [f"Request failed: {status_code}"]
                results.append(case_result)
                failed_count += 1
                continue
            field_checks = result_json.get("field_checks", [])
            
            # Validate each field
            brand_check = get_field_check(field_checks, "brand")
            if brand_check is None or not compare_brand(case["brand"], brand_check.get("label_value")):
                case_result["passed"] = False
                case_result["failed_fields"].append("brand")
            
            class_type_check = get_field_check(field_checks, "class_type")
            if class_type_check is None or not compare_class_type(case["class_type"], class_type_check.get("label_value")):
                case_result["passed"] = False
                case_result["failed_fields"].append("class_type")
            
            abv_check = get_field_check(field_checks, "abv")
            if abv_check is None or not compare_abv(case["abv"], abv_check.get("label_value")):
                case_result["passed"] = False
                case_result["failed_fields"].append("abv")
            
            net_contents_check = get_field_check(field_checks, "net_contents")
            # Combine CSV net_contents and volume_unit for comparison
            csv_net_contents = case["net_contents"]
            if csv_net_contents.upper() != "N/A":
                csv_net_contents = f"{case['net_contents']} {case['volume_unit'].lower()}"
            if net_contents_check is None or not compare_net_contents(csv_net_contents, net_contents_check.get("label_value")):
                case_result["passed"] = False
                case_result["failed_fields"].append("net_contents")
            
            warning_check = get_field_check(field_checks, "warning")
            if warning_check is None or not compare_warning(case["warning_present"], warning_check.get("label_value")):
                case_result["passed"] = False
                case_result["failed_fields"].append("warning")
            
            if case_result["passed"]:
                passed_count += 1
            else:
                failed_count += 1
            
        except Exception as e:
            case_result["passed"] = False
            case_result["failed_fields"] = [f"Error: {str(e)}"]
            failed_count += 1
        
        results.append(case_result)
    
    return {
        "total_cases": len(cases),
        "passed": passed_count,
        "failed": failed_count,
        "cases": results
    }


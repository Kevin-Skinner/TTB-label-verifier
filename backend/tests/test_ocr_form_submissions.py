"""
Pytest tests for OCR form submissions using CSV test cases.
"""
import csv
from pathlib import Path
from fastapi.testclient import TestClient
import pytest


def get_test_client():
    """Get a test client, creating it lazily to avoid import issues."""
    from app.main import app
    return TestClient(app)


def load_test_cases():
    """Load test cases from CSV file."""
    csv_path = Path(__file__).parent / "form_submissions.csv"
    cases = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cases.append(row)
    return cases


def get_field_check(field_checks, field_name):
    """Helper to locate a field check by field name."""
    for check in field_checks:
        if check["field"] == field_name:
            return check
    return None


def compare_brand(csv_brand, label_value):
    """Compare brand values case-insensitively with trimmed whitespace."""
    if label_value is None:
        return False
    csv_normalized = csv_brand.strip().lower()
    label_normalized = str(label_value).strip().lower()
    return csv_normalized == label_normalized


def compare_class_type(csv_class_type, label_value):
    """Compare class_type with exact match."""
    if label_value is None:
        return False
    return str(csv_class_type).strip() == str(label_value).strip()


def compare_abv(csv_abv, label_value):
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
        # Use pytest.approx for comparison (relative tolerance 1e-2)
        return abs(csv_float - label_float) < max(abs(csv_float) * 1e-2, 0.01)
    except (ValueError, TypeError):
        return False


def compare_net_contents(csv_net_contents, label_value):
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


def compare_warning(csv_warning, label_value):
    """Compare warning values."""
    csv_bool = csv_warning.lower() == "true"
    # label_value might be boolean or string "true"/"false"
    if label_value is None:
        return False
    label_bool = bool(label_value) if isinstance(label_value, bool) else str(label_value).lower() == "true"
    return csv_bool == label_bool


# Load test cases
test_cases = load_test_cases()


@pytest.mark.parametrize("case", test_cases)
def test_ocr_extraction(case):
    """Test OCR extraction for each CSV test case."""
    # Build image path
    images_dir = Path(__file__).parent / "images"
    image_path = images_dir / case["image"]
    
    # Verify image file exists
    assert image_path.exists(), f"Image file not found: {image_path}"
    
    # Read image bytes
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    
    # Determine content type based on file extension
    content_type = "image/jpeg"
    if image_path.suffix.lower() in [".png"]:
        content_type = "image/png"
    
    # Build form data
    # Handle ABV: if CSV has "N/A", send "n/a", otherwise send the number as string
    abv_value = "n/a" if case["abv"].upper() == "N/A" else case["abv"]
    
    # Handle net_contents: if CSV has "N/A", send "n/a", otherwise combine net_contents and volume_unit
    if case["net_contents"].upper() == "N/A":
        net_contents_value = "n/a"
    else:
        # Combine net_contents and volume_unit (e.g., "750" + "mL" -> "750 ml")
        volume_unit_lower = case["volume_unit"].lower()
        net_contents_value = f"{case['net_contents']} {volume_unit_lower}"
    
    # Convert warning_present to boolean string
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
    
    client = get_test_client()
    response = client.post("/api/verify", files=files, data=data)
    
    # Assert successful response
    assert response.status_code == 200, f"Request failed with status {response.status_code}: {response.text}"
    
    result = response.json()
    field_checks = result.get("field_checks", [])
    
    # Validate each field
    brand_check = get_field_check(field_checks, "brand")
    assert brand_check is not None, "Brand field check not found"
    assert compare_brand(case["brand"], brand_check["label_value"]), \
        f"Brand mismatch: expected '{case['brand']}', got '{brand_check['label_value']}'"
    
    class_type_check = get_field_check(field_checks, "class_type")
    assert class_type_check is not None, "Class type field check not found"
    assert compare_class_type(case["class_type"], class_type_check["label_value"]), \
        f"Class type mismatch: expected '{case['class_type']}', got '{class_type_check['label_value']}'"
    
    abv_check = get_field_check(field_checks, "abv")
    assert abv_check is not None, "ABV field check not found"
    assert compare_abv(case["abv"], abv_check["label_value"]), \
        f"ABV mismatch: expected '{case['abv']}', got '{abv_check['label_value']}'"
    
    net_contents_check = get_field_check(field_checks, "net_contents")
    assert net_contents_check is not None, "Net contents field check not found"
    # Combine CSV net_contents and volume_unit for comparison
    csv_net_contents = case["net_contents"]
    if csv_net_contents.upper() != "N/A":
        csv_net_contents = f"{case['net_contents']} {case['volume_unit'].lower()}"
    assert compare_net_contents(csv_net_contents, net_contents_check["label_value"]), \
        f"Net contents mismatch: expected '{csv_net_contents}', got '{net_contents_check['label_value']}'"
    
    warning_check = get_field_check(field_checks, "warning")
    assert warning_check is not None, "Warning field check not found"
    assert compare_warning(case["warning_present"], warning_check["label_value"]), \
        f"Warning mismatch: expected '{case['warning_present']}', got '{warning_check['label_value']}'"


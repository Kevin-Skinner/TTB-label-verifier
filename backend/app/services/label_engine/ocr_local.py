import io
import os
import re
import difflib
from typing import Any, Dict, List, Tuple, Optional

import numpy as np
from PIL import Image

from .base import LabelAnalysisEngine

# Import OCR libraries (lazy import to allow swapping engines)
_easyocr_reader = None
_paddle_ocr = None


def get_easyocr_reader():
    """
    Lazily initialize an EasyOCR reader.
    CPU-only, English for now.
    """
    global _easyocr_reader
    if _easyocr_reader is None:
        import easyocr
        _easyocr_reader = easyocr.Reader(["en"], gpu=False)
    return _easyocr_reader


def get_paddle_ocr():
    """
    Lazily initialize a PaddleOCR reader.
    CPU-only, English for now.
    Note: Requires KMP_DUPLICATE_LIB_OK=TRUE for OpenMP compatibility.
    """
    global _paddle_ocr
    if _paddle_ocr is None:
        # Set OpenMP environment variable before PaddleOCR import to avoid library conflicts
        os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
        from paddleocr import PaddleOCR
        _paddle_ocr = PaddleOCR(
            use_angle_cls=True,
            lang="en",
        )
    return _paddle_ocr


# -------------------------------------------------------------------------------------------------
# Helper functions for parsing text from the image
# -------------------------------------------------------------------------------------------------
ABV_PATTERN = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*%", re.IGNORECASE)
NET_CONTENTS_PATTERN = re.compile(
    r"(\d{2,4})\s*(ml|mL|ML|l|L|fl\s*oz)",
    re.IGNORECASE,
)

YEAR_PATTERN = re.compile(r"^(19|20)\d{2}$")  # e.g., 2018


def looks_like_year(text: str) -> bool:
    """
    Simple, non-hyper-specific year check:
    - exact 4-digit year like 2018, 2020, etc.
    We don't try to catch every variant (2018., (2018), 2 0 1 8, etc.).
    """
    return bool(YEAR_PATTERN.match(text.strip()))


def looks_like_volume(text: str) -> bool:
    return bool(NET_CONTENTS_PATTERN.search(text))


def looks_like_abv_line(text: str) -> bool:
    # check if the text has % or 'alc'
    lower = text.lower()
    return "%" in lower or "alc" in lower


def looks_like_warning(text: str) -> bool:
    return "government warning" in text.lower()


def extract_abv(text: str, class_type: Optional[str] = None) -> float | None:
    """
    Extract ABV from text, filtering out grape composition percentages.
    
    Args:
        text: Text to search for ABV
        class_type: Optional class type (e.g., 'wine') for sanity checks
        
    Returns:
        ABV value as float, or None if not found/invalid
    """
    match = ABV_PATTERN.search(text)
    if not match:
        return None
    
    # Get the matched percentage value
    abv_value = None
    try:
        abv_value = float(match.group(1))
    except ValueError:
        return None
    
    # Sanity check: if > 30% and likely wine, treat as invalid
    if abv_value > 30.0 and class_type and class_type.lower() == "wine":
        return None
    
    # Check if percentage is followed by varietal words (grape composition, not ABV)
    varietal_keywords = ["merlot", "cabernet", "shiraz", "pinot", "grape", "blend", "vintage", 
                        "chardonnay", "sauvignon", "riesling", "zinfandel", "malbec", "syrah"]
    
    # Get text after the match
    match_end = match.end()
    text_after = text[match_end:match_end + 20].lower()  # Check next 20 chars
    
    # If followed by varietal keywords, likely grape composition, not ABV
    if any(keyword in text_after for keyword in varietal_keywords):
        return None
    
    return abv_value


def extract_net_contents(text: str) -> str | None:
    match = NET_CONTENTS_PATTERN.search(text)
    if not match:
        return None
    amount, unit = match.groups()
    # Normalize unit formatting
    unit = unit.lower().replace(" ", "")
    if unit == "ml":
        unit = "ml"
    elif "floz" in unit:
        unit = "fl oz"
    elif unit == "l":
        unit = "l"
    result = f"{amount} {unit}"
    # Explicitly return None if result is empty (shouldn't happen, but safety check)
    return result if result else None


def _bbox_stats(bbox: List[List[float]]) -> tuple[float, float, float]:
    """
    Return (top_y, height, width) for a bbox.
    bbox: list of 4 points [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
    """
    xs = [p[0] for p in bbox] if bbox else [0]
    ys = [p[1] for p in bbox] if bbox else [0]
    top = float(min(ys))
    height = float(max(ys) - min(ys) or 1.0)
    width = float(max(xs) - min(xs) or 1.0)
    return top, height, width


def _bbox_center(bbox: List[List[float]]) -> tuple[float, float]:
    xs = [p[0] for p in bbox] if bbox else [0]
    ys = [p[1] for p in bbox] if bbox else [0]
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def _is_digit_dominated(text: str) -> bool:
    """
    General numeric-heavy filter, not just years.

    Idea: if a line has significantly more digits than letters (and at least 2 digits),
    it’s unlikely to be a "brand" line compared to big text like CHATEAU X, etc.
    """
    letters = sum(ch.isalpha() for ch in text)
    digits = sum(ch.isdigit() for ch in text)
    if (letters + digits) == 0:
        return False
    return digits >= 2 and digits >= letters


# -------------------------------------------------------------------------------------------------
# Guess the brand & class
# -------------------------------------------------------------------------------------------------
def guess_brand_and_class(
    results: List[Tuple[List[List[float]], str, float]],
    expected_brand: Optional[str] = None,
) -> tuple[str | None, str | None]:
    """
    results: list of (bbox, text, conf)

    Class/type:
      - Count occurrences of known class keywords across all text.
      - Choose the keyword with the highest count (majority vote).

    Brand:
      1. Prefer the largest text (by bbox height) that looks like a brand.
      2. If that fails, choose the text whose "font size" (height) is most
         different from the median height (distinctive font/size).
      3. As a last resort, fall back to the topmost plausible line.
    """
    if not results:
        return None, None
    
    # ----- Class/type majority vote -----
    CLASS_KEYWORDS: Dict[str, str] = {
        "wine": "wine",
        "beer": "beer",
        "vodka": "vodka",
        "whiskey": "whiskey",
        "whisky": "whisky",
        "rum": "rum",
        "gin": "gin",
    }

    class_counts: Dict[str, int] = {}
    first_seen_index: Dict[str, int] = {}

    for idx, (bbox, text, conf) in enumerate(results):
        lower = text.strip().lower()
        if not lower:
            continue
        for kw, canonical in CLASS_KEYWORDS.items():
            if kw in lower:
                class_counts[canonical] = class_counts.get(canonical, 0) + 1
                if canonical not in first_seen_index:
                    first_seen_index[canonical] = idx

    class_type: str | None = None
    if class_counts:
        # sort by count desc, then first appearance
        class_type = sorted(
            class_counts.keys(),
            key=lambda k: (-class_counts[k], first_seen_index[k]),
        )[0]

    # ----- Brand candidates -----
    candidates: List[Dict[str, Any]] = []
    heights: List[float] = []

    for bbox, text, conf in results:
        normalized = text.strip()
        if not normalized:
            continue

        # Skip obvious non-brand lines (generic logic)
        if looks_like_year(normalized):
            continue
        if normalized.isdigit():
            continue
        if looks_like_volume(normalized):
            continue
        if looks_like_abv_line(normalized):
            continue
        if looks_like_warning(normalized):
            continue
        if _is_digit_dominated(normalized):
            continue

        # Require at least one alphabetic character
        if not any(ch.isalpha() for ch in normalized):
            continue

        # Exclude long text lines (likely descriptions/paragraphs, not brand names)
        if len(normalized) > 40:
            continue

        top, height, width = _bbox_stats(bbox)
        # Count spaces for preference scoring (brands typically have 0-3 spaces)
        space_count = normalized.count(" ")
        candidates.append(
            {
                "text": normalized,
                "conf": float(conf),
                "top": top,
                "height": height,
                "width": width,
                "space_count": space_count,
            }
        )
        heights.append(height)

    if not candidates:
        return None, class_type

    # ----- Guided brand matching (if expected_brand provided) -----
    if expected_brand:
        expected_normalized = expected_brand.strip().lower()
        best_match = None
        best_ratio = 0.0
        
        for candidate in candidates:
            candidate_text = candidate["text"].lower()
            ratio = difflib.SequenceMatcher(None, expected_normalized, candidate_text).ratio()
            
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = candidate
        
        # If we found a high match (> 0.6), use it immediately
        if best_match and best_ratio > 0.6:
            return best_match["text"], class_type
    
    # ----- Fallback: Heuristic-based brand selection -----
    max_height = max(heights) if heights else 1.0
    median_height = sorted(heights)[len(heights) // 2] if heights else max_height

    # Phase 1: choose among the "largest" lines
    large_candidates = [
        c for c in candidates if c["height"] >= 0.9 * max_height
    ]

    def sort_brand_key(c: Dict[str, Any]) -> tuple:
        # smaller top = closer to top of label
        # negative height/conf so that larger height/conf come first
        # prefer fewer spaces (brands typically have 0-3 spaces, paragraphs have many)
        return (
            c["top"],
            -c["height"],
            c.get("space_count", 0),  # Prefer fewer spaces
            -c["conf"],
        )

    chosen: Dict[str, Any] | None = None

    if large_candidates:
        chosen = sorted(large_candidates, key=sort_brand_key)[0]
    else:
        # Phase 2: pick line whose height is most different from median
        for c in candidates:
            c["uniq"] = abs(c["height"] - median_height) / (median_height or 1.0)
        chosen = sorted(
            candidates,
            key=lambda c: (-c.get("uniq", 0.0), c["top"], -c["conf"]),
        )[0]

    brand = chosen["text"] if chosen else None
    return brand, class_type


# -------------------------------------------------------------------------------------------------
# ABV & volume logic
# -------------------------------------------------------------------------------------------------
def extract_abv_from_results(
    results: List[Tuple[List[List[float]], str, float]],
    raw_text: str,
    class_type: Optional[str] = None,
) -> float | None:
    """
    Prefer numbers that are spatially or textually close to 'ALC', 'ALCOHOL',
    and 'VOL'. Fall back to a simple regex over all text.
    Includes filtering for grape composition percentages and sanity checks.
    """
    # First: same-line matches near 'alc'/'vol'
    for bbox, text, conf in results:
        lower = text.lower()
        if "alc" in lower and ("vol" in lower or "alcohol" in lower):
            abv_value = extract_abv(text, class_type)
            if abv_value is not None:
                return abv_value

    # Second: nearest numeric neighbours to any 'alc/vol' line
    alc_boxes = [
        bbox
        for bbox, text, conf in results
        if "alc" in text.lower()
        and ("vol" in text.lower() or "alcohol" in text.lower())
    ]

    for alc_bbox in alc_boxes:
        acx, acy = _bbox_center(alc_bbox)
        numeric_candidates: List[tuple[float, str]] = []
        for bbox, text, conf in results:
            abv_value = extract_abv(text, class_type)
            if abv_value is None:
                continue
            cx, cy = _bbox_center(bbox)
            dist_sq = (cx - acx) ** 2 + (cy - acy) ** 2
            numeric_candidates.append((dist_sq, abv_value))
        if numeric_candidates:
            _, val = min(numeric_candidates, key=lambda x: x[0])
            return val

    # Fallback: plain-text extraction
    return extract_abv(raw_text, class_type)


def extract_net_contents_from_results(
    results: List[Tuple[List[List[float]], str, float]],
    raw_text: str,
) -> str | None:
    """
    Prefer numbers immediately followed by ml/L/fl oz etc on individual lines.
    If multiple candidates, pick the one with the largest volume.
    Fall back to searching the combined text.
    """
    best: str | None = None
    best_amount = -1

    for bbox, text, conf in results:
        candidate = extract_net_contents(text)
        if not candidate:
            continue
        m = re.match(r"(\d{2,4})", candidate)
        if not m:
            continue
        try:
            amount = int(m.group(1))
        except ValueError:
            continue
        if amount > best_amount:
            best_amount = amount
            best = candidate

    if best is not None:
        return best

    return extract_net_contents(raw_text)


# -------------------------------------------------------------------------------------------------
# Shared OCR result processing
# -------------------------------------------------------------------------------------------------
def process_ocr_results(
    results: List[Tuple[List[List[float]], str, float]],
    expected_brand: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Process normalized OCR results into structured label data.
    This shared function is used by all OCR engines.
    
    Args:
        results: List of (bbox, text, confidence) tuples
        expected_brand: Optional expected brand name for guided matching
        
    Returns:
        Dictionary with raw_text, extracted fields, and confidence metrics
    """
    texts = [t for _, t, _ in results]
    confs = [c for _, _, c in results]

    raw_text = " ".join(texts)
    avg_conf = float(sum(confs) / len(confs)) if confs else 0.0
    min_conf = float(min(confs)) if confs else 0.0

    # Extract structured fields from both layout and combined raw text
    lower_text = raw_text.lower()

    # First guess class_type for ABV sanity checks
    brand, class_type = guess_brand_and_class(results, expected_brand=expected_brand)
    
    # Extract ABV with class_type for sanity checks
    abv = extract_abv_from_results(results, raw_text, class_type=class_type)
    net_contents = extract_net_contents_from_results(results, raw_text)
    
    # Check for warning phrases (more robust than single phrase check)
    warning_phrases = [
        "government warning",
        "surgeon general",
        "during pregnancy",
        "health problems",
    ]
    warning_present = any(phrase in lower_text for phrase in warning_phrases)

    extracted = {
        "brand": brand,
        "abv": abv,
        "class_type": class_type,
        "net_contents": net_contents,
        "warning_present": warning_present,
    }

    confidence = {
        "avg_conf": avg_conf,
        "min_conf": min_conf,
        "num_tokens": len(results),
    }

    return {
        "raw_text": raw_text,
        "extracted": extracted,
        "confidence": confidence,
    }


# -------------------------------------------------------------------------------------------------
# OCR Engines
# -------------------------------------------------------------------------------------------------
class EasyOCREngine(LabelAnalysisEngine):
    """
    OCR-based engine using EasyOCR.
    analyze(image_bytes) -> dict
    """

    async def analyze(self, image_bytes: bytes, **kwargs) -> Dict[str, Any]:
        # Load image from bytes
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image_np = np.array(image)

        reader = get_easyocr_reader()
        # EasyOCR returns: list of (bbox, text, conf) tuples with detail=1
        # bbox format: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        raw_results = reader.readtext(image_np, detail=1)

        # Normalize to list of (bbox, text, conf)
        results: List[Tuple[List[List[float]], str, float]] = []
        for bbox, text, conf in raw_results:
            # Ensure bbox is in the shape [[x,y], [x,y], [x,y], [x,y]]
            try:
                normalized_bbox = [[float(p[0]), float(p[1])] for p in bbox]
                results.append((normalized_bbox, str(text), float(conf)))
            except (ValueError, TypeError, IndexError):
                # Skip if bbox conversion fails
                continue

        expected_brand = kwargs.get("expected_brand")
        return process_ocr_results(results, expected_brand=expected_brand)


class PaddleOCREngine(LabelAnalysisEngine):
    """
    OCR-based engine using PaddleOCR.
    analyze(image_bytes) -> dict
    """

    async def analyze(self, image_bytes: bytes, **kwargs) -> Dict[str, Any]:
        # Load image from bytes
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image_np = np.array(image)

        ocr = get_paddle_ocr()
        # PaddleOCR returns various formats depending on version
        raw_result = ocr.ocr(image_np)

        # Debug: Log raw result structure
        print(f"[DEBUG] Raw result type: {type(raw_result)}")
        print(f"[DEBUG] Raw result length: {len(raw_result) if raw_result else 0}")
        if raw_result and len(raw_result) > 0:
            print(f"[DEBUG] First element type: {type(raw_result[0])}")
            if isinstance(raw_result[0], dict):
                print(f"[DEBUG] First element keys: {list(raw_result[0].keys())}")

        results: List[Tuple[List[List[float]], str, float]] = []

        # Handle PaddleOCR OCRResult format with parallel lists (PaddleX structure)
        if raw_result and len(raw_result) > 0:
            res = raw_result[0]
            
            # Check if this is the OCRResult format with parallel lists
            if isinstance(res, dict) and "rec_texts" in res:
                texts = res.get("rec_texts", [])
                scores = res.get("rec_scores", [])
                boxes = res.get("dt_polys", [])
                
                print(f"[DEBUG] Using parallel lists format - texts: {len(texts)}, scores: {len(scores)}, boxes: {len(boxes)}")
                
                # Iterate through parallel lists using zip
                for text, score, box in zip(texts, scores, boxes):
                    # NumPy-safe check: box might be a NumPy array, so check None and length explicitly
                    if box is None or len(box) == 0 or text is None or score is None:
                        continue
                    
                    # Ensure bbox is in the shape [[x,y], [x,y], [x,y], [x,y]]
                    try:
                        bbox = [[float(p[0]), float(p[1])] for p in box]
                        results.append((bbox, str(text), float(score)))
                    except (ValueError, TypeError, IndexError):
                        # Skip if bbox conversion fails
                        print(f"[DEBUG] Skipping - bbox conversion failed for text: {text}")
                        continue
            
            # Legacy fallback: Handle list/tuple formats
            else:
                print(f"[DEBUG] Using legacy format fallback")
                paddle_lines = res if isinstance(res, list) else raw_result
                
                if paddle_lines:
                    for idx, line in enumerate(paddle_lines):
                        if not line:
                            continue
                        
                        # Debug: Log line structure
                        print(f"[DEBUG] Line {idx} type: {type(line)}")
                        if isinstance(line, dict):
                            print(f"[DEBUG] Line {idx} keys: {list(line.keys())}")
                            print(f"[DEBUG] Line {idx} full content: {line}")
                        elif isinstance(line, (list, tuple)):
                            print(f"[DEBUG] Line {idx} length: {len(line)}")
                            print(f"[DEBUG] Line {idx} content: {line}")
                        
                        box = None
                        text = None
                        score = None
                        
                        # Handle dictionary format (PaddleOCR v5+)
                        if isinstance(line, dict):
                            # PaddleOCR v5 uses: transcription, confidence, points (or dt_polys)
                            # Try common key variations for text, score, and box
                            text = (line.get("transcription") or line.get("rec_text") or 
                                   line.get("text") or line.get("txt") or line.get("content"))
                            score = (line.get("confidence") or line.get("rec_score") or 
                                    line.get("score") or line.get("conf"))
                            box = (line.get("points") or line.get("dt_polys") or 
                                  line.get("box") or line.get("bbox") or line.get("poly"))
                            
                            print(f"[DEBUG] Extracted - text: {text}, score: {score}, box: {box}")
                            
                            if not all([box, text is not None, score is not None]):
                                # Skip if we can't extract required fields
                                print(f"[DEBUG] Skipping line {idx} - missing required fields")
                                continue
                        
                        # Handle list/tuple formats (legacy PaddleOCR)
                        elif isinstance(line, (list, tuple)):
                            try:
                                if len(line) >= 2 and isinstance(line[1], tuple):
                                    # Format 1: [box, (text, score)]
                                    box, (text, score) = line
                                elif len(line) >= 3:
                                    # Format 2: [box, text, score, ...]
                                    box, text, score = line[0], line[1], line[2]
                                else:
                                    continue
                            except (ValueError, TypeError, IndexError):
                                # Skip lines that don't match expected formats
                                continue
                        else:
                            # Unknown format, skip
                            continue
                        
                        # Ensure bbox is in the shape [[x,y], [x,y], [x,y], [x,y]]
                        try:
                            bbox = [[float(p[0]), float(p[1])] for p in box]
                            results.append((bbox, str(text), float(score)))
                        except (ValueError, TypeError, IndexError):
                            # Skip if bbox conversion fails
                            continue

        expected_brand = kwargs.get("expected_brand")
        return process_ocr_results(results, expected_brand=expected_brand)


class DummyOCREngine(LabelAnalysisEngine):
    """
    Simple dummy engine for testing / when USE_DUMMY_ENGINE=true.
    """

    async def analyze(self, image_bytes: bytes, **kwargs) -> Dict[str, Any]:
        return {
            "raw_text": "",
            "extracted": {
                "brand": None,
                "abv": None,
                "class_type": None,
                "net_contents": None,
                "warning_present": False,
            },
            "confidence": {
                "avg_conf": 0.0,
                "min_conf": 0.0,
                "num_tokens": 0,
            },
        }


# -------------------------------------------------------------------------------------------------
# Engine factory to get the appropriate engine
# -------------------------------------------------------------------------------------------------
USE_DUMMY_ENGINE = os.getenv("USE_DUMMY_ENGINE", "false").lower() == "true"
OCR_ENGINE = os.getenv("OCR_ENGINE", "paddleocr").lower()  # Options: "easyocr", "paddleocr"


def get_label_engine():
    """
    Return the current label analysis engine.
    
    Environment variables:
    - USE_DUMMY_ENGINE=true: Use DummyOCREngine (for testing)
    - OCR_ENGINE=paddleocr: Use PaddleOCREngine (default)
    - OCR_ENGINE=easyocr: Use EasyOCREngine
    
    Default: PaddleOCREngine
    """
    if USE_DUMMY_ENGINE:
        return DummyOCREngine()
    
    if OCR_ENGINE == "easyocr":
        return EasyOCREngine()
    
    # Default to PaddleOCR
    return PaddleOCREngine()

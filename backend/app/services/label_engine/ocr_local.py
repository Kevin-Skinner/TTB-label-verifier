import io
import os
import re
import difflib
import logging
from typing import Any, Dict, List, Tuple, Optional

import numpy as np
from PIL import Image

from .base import LabelAnalysisEngine

logger = logging.getLogger(__name__)

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
    lower = text.lower()
    return (
        "government warning" in lower or
        "warning" in lower or
        "pregnancy" in lower
    )


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


def _bbox_left(bbox: List[List[float]]) -> float:
    """Return the leftmost x coordinate of the bbox."""
    xs = [p[0] for p in bbox] if bbox else [0]
    return float(min(xs))


def _bbox_right(bbox: List[List[float]]) -> float:
    """Return the rightmost x coordinate of the bbox."""
    xs = [p[0] for p in bbox] if bbox else [0]
    return float(max(xs))


def _bbox_top(bbox: List[List[float]]) -> float:
    """Return the topmost y coordinate of the bbox."""
    ys = [p[1] for p in bbox] if bbox else [0]
    return float(min(ys))


def _bbox_bottom(bbox: List[List[float]]) -> float:
    """Return the bottommost y coordinate of the bbox."""
    ys = [p[1] for p in bbox] if bbox else [0]
    return float(max(ys))


def _is_digit_dominated(text: str) -> bool:
    """
    General numeric-heavy filter, not just years.

    Idea: if a line has significantly more digits than letters (and at least 2 digits),
    it's unlikely to be a "brand" line compared to big text like CHATEAU X, etc.
    """
    letters = sum(ch.isalpha() for ch in text)
    digits = sum(ch.isdigit() for ch in text)
    if (letters + digits) == 0:
        return False
    return digits >= 2 and digits >= letters


def _slugify_brand(brand: str) -> str:
    """
    Convert brand name to a slugified version (lowercase, no spaces, no special chars).
    Used for searching in URLs like "theprisonerwine.com".
    """
    # Remove common words that might not be in URLs
    brand_lower = brand.lower().strip()
    # Remove spaces and common punctuation
    slug = re.sub(r'[^\w]', '', brand_lower)
    return slug


# -------------------------------------------------------------------------------------------------
# Brand line expansion helper
# -------------------------------------------------------------------------------------------------
def _expand_brand_line(anchor: Dict[str, Any], candidates: List[Dict[str, Any]]) -> tuple[str, List[List[List[float]]]]:
    """
    Expand the anchor brand candidate to include same-line neighbors (Phase 1)
    and stacked suffix lines below (Phase 2).
    
    Args:
        anchor: The chosen best candidate (dict with text, bbox, height, top, width, etc.)
        candidates: The full candidate list used in scoring
        
    Returns:
        Expanded brand text (e.g., "LA PULGA", "STAG'S LEAP WINE CELLARS", or "ST. GEORGE SPIRITS")
    """
    # Phase 1 constants (horizontal expansion)
    HEIGHT_RATIO_MIN = 0.8   # similar height
    HEIGHT_RATIO_MAX = 1.2
    MAX_VERTICAL_OFFSET_FACTOR = 0.3  # same line if center y diff < 0.3 * anchor_height
    MAX_H_GAP_FACTOR = 1.0           # max horizontal gap in terms of anchor_height
    
    PREFIX_WHITELIST = {"la", "el", "los", "las", "the", "le", "de", "di", "da", "do"}
    MAX_JOINED_WORDS = 5
    
    # Phase 2 constants (stacked suffix expansion)
    STACK_MAX_VERTICAL_GAP_FACTOR = 1.2  # how far below the brand line we look (in units of line_height)
    STACK_HEIGHT_RATIO_MIN = 0.7
    STACK_HEIGHT_RATIO_MAX = 1.3
    STACK_CENTER_OFFSET_FACTOR = 1.0     # how far horizontally from the center we allow (in units of line_height)
    
    STACK_SUFFIX_WHITELIST = {
        "spirits",
        "distillery", "distilling", "distilling co", "distilling company",
        "wine cellars", "cellars", "vineyards", "vineyard", "winery",
        "brewing company", "brewery", "brewing", "malt beverages", "beer", "ale"
    }
    
    # Get anchor geometry
    anchor_bbox = anchor.get("bbox")
    if not anchor_bbox:
        text = anchor.get("text", "")
        return text, [anchor_bbox] if anchor_bbox else []
    
    anchor_text = anchor.get("text", "").strip()
    anchor_height = anchor.get("height", 1.0)
    anchor_cx, anchor_cy = _bbox_center(anchor_bbox)
    
    if not anchor_text:
        return anchor_text, [anchor_bbox] if anchor_bbox else []
    
    # Find same-line neighbors
    neighbors: List[Dict[str, Any]] = []
    
    for c in candidates:
        # Skip if c is anchor (compare by text and position to avoid reference issues)
        if (c.get("text", "").strip() == anchor_text and 
            abs(c.get("center_x", 0) - anchor_cx) < 1.0 and
            abs(c.get("center_y", 0) - anchor_cy) < 1.0):
            continue
        
        c_text = c.get("text", "").strip()
        if not c_text:
            continue
        
        c_bbox = c.get("bbox")
        if not c_bbox:
            continue
        
        c_height = c.get("height", 1.0)
        c_cx, c_cy = _bbox_center(c_bbox)
        
        # Check similar height
        ratio = c_height / (anchor_height or 1.0)
        if ratio < HEIGHT_RATIO_MIN or ratio > HEIGHT_RATIO_MAX:
            continue
        
        # Check same line: vertical offset small
        if abs(c_cy - anchor_cy) > MAX_VERTICAL_OFFSET_FACTOR * anchor_height:
            continue
        
        # This candidate is on the same line and similar size
        neighbors.append(c)
    
    # Build line_candidates including anchor
    line_candidates = neighbors + [anchor]
    
    # Compute and store left/right for each
    for cand in line_candidates:
        bbox = cand.get("bbox")
        if bbox:
            cand["left"] = _bbox_left(bbox)
            cand["right"] = _bbox_right(bbox)
            cand["cx"] = _bbox_center(bbox)[0]
    
    # Sort by center x ascending
    line_candidates.sort(key=lambda c: c.get("cx", 0))
    
    # Find anchor index and get anchor from sorted list
    anchor_idx = -1
    anchor_in_list = None
    for idx, cand in enumerate(line_candidates):
        if (cand.get("text", "").strip() == anchor_text and
            abs(cand.get("cx", 0) - anchor_cx) < 1.0):
            anchor_idx = idx
            anchor_in_list = cand
            break
    
    if anchor_idx == -1 or anchor_in_list is None:
        # Anchor not found in sorted list (shouldn't happen), return anchor text
        return anchor_text, [anchor_bbox] if anchor_bbox else []
    
    # Build contiguous run around anchor (use anchor from sorted list)
    run = [anchor_in_list]
    
    # Expand left
    for idx in range(anchor_idx - 1, -1, -1):
        cand = line_candidates[idx]
        run_left = run[0]
        
        # Compute horizontal gap
        gap = run_left.get("left", 0) - cand.get("right", 0)
        if gap > MAX_H_GAP_FACTOR * anchor_height:
            break
        
        # Normalize text
        token = cand.get("text", "").strip()
        token_lower = token.lower()
        
        # For left-side, only accept if short or in prefix whitelist
        if len(token_lower) <= 3 or token_lower in PREFIX_WHITELIST:
            run.insert(0, cand)
        else:
            break
    
    # Expand right
    for idx in range(anchor_idx + 1, len(line_candidates)):
        cand = line_candidates[idx]
        run_right = run[-1]
        
        # Compute horizontal gap
        gap = cand.get("left", 0) - run_right.get("right", 0)
        if gap > MAX_H_GAP_FACTOR * anchor_height:
            break
        
        # Normalize text
        token = cand.get("text", "").strip()
        token_lower = token.lower()
        
        # For right-side, accept if alphabetic and reasonably short
        if token and all(ch.isalpha() or ch.isspace() or ch in "'-" for ch in token) and len(token) <= 16:
            run.append(cand)
        else:
            break
    
    # Truncate if too long (keep anchor in middle if possible)
    if len(run) > MAX_JOINED_WORDS:
        # Find anchor position in run
        anchor_in_run_idx = -1
        for idx, cand in enumerate(run):
            if (cand.get("text", "").strip() == anchor_text and
                abs(cand.get("cx", 0) - anchor_cx) < 1.0):
                anchor_in_run_idx = idx
                break
        
        if anchor_in_run_idx >= 0:
            # Keep anchor and balance around it
            half = MAX_JOINED_WORDS // 2
            start = max(0, anchor_in_run_idx - half)
            end = min(len(run), start + MAX_JOINED_WORDS)
            run = run[start:end]
        else:
            # Fallback: just take first MAX_JOINED_WORDS (shouldn't happen, but safety)
            run = run[:MAX_JOINED_WORDS]
    
    # Build final brand string from horizontal expansion (Phase 1)
    expanded_parts = [c.get("text", "").strip() for c in run if c.get("text", "").strip()]
    line_text = " ".join(expanded_parts)
    
    # Collect boxes from horizontal expansion
    horizontal_boxes = [c.get("bbox") for c in run if c.get("bbox")]
    
    # Fallback to anchor if expanded is empty
    if not line_text:
        line_text = anchor_text
        horizontal_boxes = [anchor_bbox] if anchor_bbox else []
    
    # Phase 2: Find and append stacked suffix lines
    # Compute combined line geometry from the horizontally-expanded run
    if not run or not all(c.get("bbox") for c in run):
        return line_text, horizontal_boxes
    
    line_left = min(_bbox_left(c.get("bbox")) for c in run if c.get("bbox"))
    line_right = max(_bbox_right(c.get("bbox")) for c in run if c.get("bbox"))
    line_top = min(_bbox_top(c.get("bbox")) for c in run if c.get("bbox"))
    line_bottom = max(_bbox_bottom(c.get("bbox")) for c in run if c.get("bbox"))
    line_height = line_bottom - line_top
    line_cx = (line_left + line_right) / 2.0
    
    if line_height <= 0:
        return line_text, horizontal_boxes
    
    # Track which boxes are already part of the brand line run (to avoid duplicates)
    run_boxes = set()
    for c in run:
        bbox = c.get("bbox")
        if bbox:
            # Use a simple identifier: (center_x, center_y) rounded to nearest integer
            cx, cy = _bbox_center(bbox)
            run_boxes.add((round(cx), round(cy)))
    
    # Find candidate stacked lines
    stacked_candidates: List[Dict[str, Any]] = []
    
    for c in candidates:
        # Skip if already part of the brand line run
        c_bbox = c.get("bbox")
        if not c_bbox:
            continue
        
        cx, cy = _bbox_center(c_bbox)
        c_key = (round(cx), round(cy))
        if c_key in run_boxes:
            continue
        
        c_text = c.get("text", "").strip()
        if not c_text:
            continue
        
        c_height = c.get("height", 1.0)
        c_top = _bbox_top(c_bbox)
        
        # Must be below the brand line but not too far
        vertical_gap = c_top - line_bottom
        if vertical_gap <= 0:
            continue
        if vertical_gap > STACK_MAX_VERTICAL_GAP_FACTOR * line_height:
            continue
        
        # Must be similar height
        ratio = c_height / (line_height or 1.0)
        if ratio < STACK_HEIGHT_RATIO_MIN or ratio > STACK_HEIGHT_RATIO_MAX:
            continue
        
        # Must be reasonably centered horizontally
        if abs(cx - line_cx) > STACK_CENTER_OFFSET_FACTOR * line_height:
            continue
        
        # Apply suffix whitelist
        token = c_text
        token_lower = token.lower()
        # Normalize: remove trailing punctuation
        token_lower = token_lower.rstrip(".,;:!?")
        
        # Check if token matches whitelist (exact match or starts with whitelist phrase)
        is_allowed = False
        if token_lower in STACK_SUFFIX_WHITELIST:
            is_allowed = True
        else:
            # Check if it starts with any whitelist phrase (followed by space or end of string)
            for whitelist_phrase in STACK_SUFFIX_WHITELIST:
                if (token_lower == whitelist_phrase or 
                    token_lower.startswith(whitelist_phrase + " ")):
                    is_allowed = True
                    break
        
        if is_allowed:
            stacked_candidates.append(c)
    
    # Sort and append stacked candidates
    all_boxes = horizontal_boxes.copy()
    if stacked_candidates:
        stacked_candidates.sort(key=lambda c: _bbox_top(c.get("bbox")) if c.get("bbox") else 0)
        suffix_texts = [c.get("text", "").strip() for c in stacked_candidates if c.get("text", "").strip()]
        if suffix_texts:
            brand_text = " ".join([line_text] + suffix_texts).strip()
            # Add stacked boxes
            stacked_boxes = [c.get("bbox") for c in stacked_candidates if c.get("bbox")]
            all_boxes.extend(stacked_boxes)
            return brand_text, all_boxes
    
    return line_text, all_boxes


# -------------------------------------------------------------------------------------------------
# Guess the brand & class
# -------------------------------------------------------------------------------------------------
def guess_brand_and_class(
    results: List[Tuple[List[List[float]], str, float]],
    expected_brand: Optional[str] = None,
) -> tuple[str | None, str | None, List[List[List[float]]], List[List[List[float]]]]:
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
        return None, None, [], []
    
    # ----- Class/type hierarchical keyword scoring -----
    # Build raw_text for class detection
    raw_text = " ".join([t for _, t, _ in results]).lower()
    
    # Normalize text: lowercase, strip punctuation for matching
    def normalize_for_match(text: str) -> str:
        # Remove punctuation, normalize spaces
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    normalized_text = normalize_for_match(raw_text)
    
    # Define keyword sets with weights
    # Distilled Spirits keywords
    spirits_primary = [
        "spirits", "distilled spirits", "neutral spirits", "grain spirits",
        "vodka", "whisky", "whiskey", "bourbon", "rye", "scotch",
        "gin", "brandy", "cognac", "armagnac", "rum", "rhum",
        "cachaça", "cachaca", "tequila", "mezcal", "agave spirit",
        "sotol", "liqueur", "cordial", "absinthe", "akvavit", "aquavit",
        "arrack", "kirsch", "kirschwasser", "slivovitz", "grappa",
        "pisco", "calvados", "applejack", "bitters",
        "moonshine", "schnapps", "genever",
        "shochu", "baijiu", "soju"
    ]
    
    spirits_contextual = [
        "distilled by", "blended by", "single malt", "single barrel",
        "small batch", "cask strength", "proof",
        "aged", "aged", "non-chill filtered",
        "bottled in bond", "reposado", "añejo", "anejo", "blanco",
        "v.s.", "v.s.o.p.", "x.o."
    ]
    
    # Wine keywords
    wine_primary = [
        "wine", "table wine", "dessert wine", "sparkling wine",
        "champagne", "carbonated wine", "vermouth",
        "cider", "hard cider", "perry",
        "mead", "honey wine", "sake",
        "sherry", "port", "porto", "madeira", "marsala",
        "tokay", "tokaji", "retsina", "aperitif wine",
        "sangria", "mistelle"
    ]
    
    wine_varietals = [
        "cabernet sauvignon", "chardonnay", "merlot",
        "pinot noir", "pinot grigio", "pinot gris",
        "sauvignon blanc", "riesling", "zinfandel",
        "syrah", "shiraz", "malbec", "grenache", "garnacha",
        "tempranillo", "sangiovese",
        "moscato", "muscat",
        "rose", "rosé", "prosecco", "cava", "lambrusco"
    ]
    
    wine_contextual = [
        "vinted by", "cellared by", "vintage", "estate bottled",
        "grown, produced, and bottled by",
        "appellation", "ava",
        "contains sulfites",
        "sec", "demi-sec", "brut", "extra dry",
        "cuvée", "cuvee",
        "late harvest", "ice wine", "eiswein",
        "sur lie", "old vine"
    ]
    
    # Malt Beverages keywords
    malt_primary = [
        "malt beverage", "beer", "ale", "lager",
        "stout", "porter", "pilsner", "pilsener",
        "bock", "doppelbock",
        "hefeweizen", "weizen", "wheat beer",
        "kolsch", "kölsch",
        "saison", "gose", "lambic",
        "barleywine", "malt liquor",
        "hard seltzer",
        "root beer"
    ]
    
    malt_contextual = [
        "brewed by", "brewing company", "brewery",
        "ipa", "india pale ale", "double ipa", "dipa",
        "hops", "hopped", "dry hopped",
        "malt", "malted",
        "ibu", "draft", "draught",
        "craft beer", "microbrew",
        "imperial", "session", "nitro",
        "tripel", "dubbel", "quadrupel",
        "sour"
    ]
    
    # Score each class and collect bounding boxes for contributing results
    score_spirits = 0
    score_wine = 0
    score_malt = 0
    class_type_boxes: List[List[List[float]]] = []
    
    # Collect all keywords that will be checked
    all_keywords = spirits_primary + spirits_contextual + wine_primary + wine_varietals + wine_contextual + malt_primary + malt_contextual
    
    # Check for spirits keywords
    for keyword in spirits_primary:
        if keyword in normalized_text:
            score_spirits += 3
            # Find OCR results containing this keyword
            for bbox, text, conf in results:
                text_lower = text.lower()
                if keyword in text_lower and bbox not in class_type_boxes:
                    class_type_boxes.append(bbox)
    
    for keyword in spirits_contextual:
        if keyword in normalized_text:
            score_spirits += 1
            # Find OCR results containing this keyword
            for bbox, text, conf in results:
                text_lower = text.lower()
                if keyword in text_lower and bbox not in class_type_boxes:
                    class_type_boxes.append(bbox)
    
    # Special handling for "alcohol" - only count if not followed by "%" or "by volume"
    if "alcohol" in normalized_text:
        # Simple heuristic: check if line contains alcohol but not % or by volume
        for bbox, text, conf in results:
            text_lower = text.lower()
            if "alcohol" in text_lower and "%" not in text_lower and "by volume" not in text_lower:
                score_spirits += 1
                if bbox not in class_type_boxes:
                    class_type_boxes.append(bbox)
                break
    
    # Check for wine keywords
    for keyword in wine_primary:
        if keyword in normalized_text:
            score_wine += 3
            # Find OCR results containing this keyword
            for bbox, text, conf in results:
                text_lower = text.lower()
                if keyword in text_lower and bbox not in class_type_boxes:
                    class_type_boxes.append(bbox)
    
    for keyword in wine_varietals:
        if keyword in normalized_text:
            score_wine += 3  # Varietals are strong indicators
            # Find OCR results containing this keyword
            for bbox, text, conf in results:
                text_lower = text.lower()
                if keyword in text_lower and bbox not in class_type_boxes:
                    class_type_boxes.append(bbox)
    
    for keyword in wine_contextual:
        if keyword in normalized_text:
            score_wine += 1
            # Find OCR results containing this keyword
            for bbox, text, conf in results:
                text_lower = text.lower()
                if keyword in text_lower and bbox not in class_type_boxes:
                    class_type_boxes.append(bbox)
    
    # Check for malt beverage keywords
    for keyword in malt_primary:
        if keyword in normalized_text:
            score_malt += 3
            # Find OCR results containing this keyword
            for bbox, text, conf in results:
                text_lower = text.lower()
                if keyword in text_lower and bbox not in class_type_boxes:
                    class_type_boxes.append(bbox)
    
    for keyword in malt_contextual:
        if keyword in normalized_text:
            score_malt += 1
            # Find OCR results containing this keyword
            for bbox, text, conf in results:
                text_lower = text.lower()
                if keyword in text_lower and bbox not in class_type_boxes:
                    class_type_boxes.append(bbox)
    
    # Determine class_type based on scores (priority: Spirits > Wine > Malt)
    class_type: str | None = None
    
    if score_spirits > 0 or score_wine > 0 or score_malt > 0:
        if score_spirits >= score_wine and score_spirits >= score_malt:
            class_type = "Distilled Spirits"
        elif score_wine >= score_malt:
            class_type = "Wine"
        else:
            class_type = "Malt Beverages"

    # ----- Brand candidates -----
    candidates: List[Dict[str, Any]] = []
    heights: List[float] = []
    
    # Build raw_text for brand name searching in URLs
    raw_text = " ".join([t for _, t, _ in results]).lower()
    
    # Collect all heights first to calculate median for filtering
    all_heights: List[float] = []
    for bbox, text, conf in results:
        _, height, _ = _bbox_stats(bbox)
        all_heights.append(height)
    median_height_all = sorted(all_heights)[len(all_heights) // 2] if all_heights else 1.0

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

        top, height, width = _bbox_stats(bbox)
        cx, cy = _bbox_center(bbox)
        
        # Updated length filtering: increased to 60, with font height check for long lines
        line_length = len(normalized)
        if line_length > 60:
            continue
        
        # For long lines (20+ chars), check if it's a header (large font) vs body text (small font)
        if line_length >= 20:
            # Compare height to median - if significantly larger, it's likely a header
            # If it's long but has small font height (relative to median), it's likely body text
            height_ratio = height / (median_height_all or 1.0)
            # If height is less than 1.2x median, it's likely body text, so skip it
            if height_ratio < 1.2:
                continue

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
                "center_x": cx,
                "center_y": cy,
                "bbox": bbox,  # Store bbox for line expansion
            }
        )
        heights.append(height)

    if not candidates:
        return None, class_type, [], []

    # ----- Guided brand matching (if expected_brand provided) -----
    if expected_brand:
        expected_normalized = expected_brand.strip().lower()
        expected_slug = _slugify_brand(expected_brand)
        best_match = None
        best_ratio = 0.0
        
        # If expected_brand is long, prioritize finding the full string
        is_long_brand = len(expected_normalized) >= 20
        
        for candidate in candidates:
            candidate_text = candidate["text"].lower()
            ratio = difflib.SequenceMatcher(None, expected_normalized, candidate_text).ratio()
            
            # Boost priority for long expected brands that match the full string
            priority_boost = 0.0
            if is_long_brand and len(candidate_text) >= len(expected_normalized) * 0.8:
                priority_boost = 0.1  # Small boost to prioritize longer matches
            
            adjusted_ratio = ratio + priority_boost
            
            if adjusted_ratio > best_ratio:
                best_ratio = ratio  # Keep original ratio for threshold checks
                best_match = candidate
        
        # If we found a high match (> 0.80), use it immediately
        if best_match and best_ratio > 0.80:
            brand, brand_boxes = _expand_brand_line(best_match, candidates)
            return brand, class_type, brand_boxes, class_type_boxes
        
        # For imperfect matches (0.70-0.80), check if brand appears elsewhere in raw text
        if best_match and 0.70 <= best_ratio <= 0.80:
            # Search for brand name or slugified version in raw text
            brand_found_in_text = (
                expected_normalized in raw_text or
                expected_slug in raw_text or
                expected_normalized.replace(" ", "") in raw_text
            )
            
            if brand_found_in_text:
                # Boost confidence and accept the imperfect fuzzy match
                brand, brand_boxes = _expand_brand_line(best_match, candidates)
                return brand, class_type, brand_boxes, class_type_boxes
    
    # ----- Fallback: Heuristic-based brand selection with relative scoring -----
    # Constants for scoring weights and tier thresholds
    EPS = 1e-6
    TIER1_MAX_Y = 0.35  # top ~35% of label
    TIER2_MAX_Y = 0.70  # upper + mid ~70% of label
    
    # Scoring weights
    WEIGHT_SIZE = 0.35
    WEIGHT_DENSITY = 0.25
    WEIGHT_WORDS = 0.20
    WEIGHT_T_POSITION = 0.10
    WEIGHT_DISTINCT = 0.10
    
    # Compute common stats over candidates
    heights = [c["height"] for c in candidates]
    median_height = sorted(heights)[len(heights) // 2] if heights else 1.0
    min_height = min(heights) if heights else 1.0
    max_height = max(heights) if heights else 1.0
    
    # Compute word counts and densities for all candidates
    for c in candidates:
        text = c["text"]
        num_chars = len(text.strip())
        num_words = len(text.split())
        area = max(c["height"] * c["width"], 1.0)
        char_density = num_chars / area
        
        c["num_words"] = num_words
        c["char_density"] = char_density
        c["num_chars"] = num_chars
        c["area"] = area
    
    # Compute ranges for normalization
    word_counts = [c["num_words"] for c in candidates]
    densities = [c["char_density"] for c in candidates]
    tops = [c["top"] for c in candidates]
    center_xs = [c["center_x"] for c in candidates]
    
    min_words = min(word_counts) if word_counts else 0
    max_words = max(word_counts) if word_counts else 1
    min_density = min(densities) if densities else 0.0
    max_density = max(densities) if densities else 1.0
    min_top = min(tops) if tops else 0.0
    max_top = max(tops) if tops else 1.0
    min_cx = min(center_xs) if center_xs else 0.0
    max_cx = max(center_xs) if center_xs else 1.0
    
    # Compute features for each candidate
    for c in candidates:
        text = c["text"]
        top = c["top"]
        height = c["height"]
        width = c["width"]
        num_words = c["num_words"]
        char_density = c["char_density"]
        cx = c["center_x"]
        
        # Normalize vertical & horizontal position
        y_norm = (top - min_top) / (max_top - min_top + EPS) if (max_top - min_top) > EPS else 0.0
        cx_norm = (cx - min_cx) / (max_cx - min_cx + EPS) if (max_cx - min_cx) > EPS else 0.5
        
        # T-shape scores
        top_score = 1.0 - y_norm
        stem_score = 1.0 - abs(cx_norm - 0.5) / 0.5 if abs(cx_norm - 0.5) > EPS else 1.0
        T_score = 0.7 * top_score + 0.3 * stem_score
        
        # Size score (relative bbox height)
        if max_height > min_height:
            size_score = (height - min_height) / (max_height - min_height + EPS)
        else:
            size_score = 1.0
        
        # Word count score (fewer words is better)
        word_span = max_words - min_words if (max_words - min_words) > 0 else 1.0
        words_score = (max_words - num_words) / word_span if word_span > EPS else 1.0
        
        # Density score (lower char density is better)
        density_span = max_density - min_density if (max_density - min_density) > EPS else 1.0
        density_score = (max_density - char_density) / density_span if density_span > EPS else 1.0
        
        # Distinctiveness score (height deviation from median)
        distinct_height = abs(height - median_height) / (median_height or 1.0)
        max_distinct = max(
            (abs(h - median_height) / (median_height or 1.0) for h in heights),
            default=1.0
        )
        distinct_score = distinct_height / max_distinct if max_distinct > EPS else 0.0
        
        # Store scores
        c["y_norm"] = y_norm
        c["cx_norm"] = cx_norm
        c["top_score"] = top_score
        c["stem_score"] = stem_score
        c["T_score"] = T_score
        c["size_score"] = size_score
        c["words_score"] = words_score
        c["density_score"] = density_score
        c["distinct_score"] = distinct_score
        
        # Compute final brand_score
        brand_score = (
            WEIGHT_SIZE * size_score +
            WEIGHT_DENSITY * density_score +
            WEIGHT_WORDS * words_score +
            WEIGHT_T_POSITION * T_score +
            WEIGHT_DISTINCT * distinct_score
        )
        c["brand_score"] = brand_score
    
    # Tiered T-search
    tier1_candidates = [c for c in candidates if c["y_norm"] <= TIER1_MAX_Y]
    tier2_candidates = [c for c in candidates if c["y_norm"] <= TIER2_MAX_Y]
    
    # Select active tier
    if tier1_candidates:
        active_candidates = tier1_candidates
        tier_name = "tier1"
    elif tier2_candidates:
        active_candidates = tier2_candidates
        tier_name = "tier2"
    else:
        active_candidates = candidates
        tier_name = "fallback"
    
    # Select candidate with highest brand_score
    chosen = max(active_candidates, key=lambda c: c["brand_score"])
    
    # Optional debug logging (can be enabled via logger.debug)
    logger.debug(
        f"Brand selection: '{chosen['text']}' from {tier_name} "
        f"(score={chosen['brand_score']:.3f}, "
        f"size={chosen['size_score']:.3f}, "
        f"density={chosen['density_score']:.3f}, "
        f"words={chosen['words_score']:.3f}, "
        f"T={chosen['T_score']:.3f}, "
        f"distinct={chosen['distinct_score']:.3f})"
    )
    
    # Expand brand to include same-line neighbors
    brand, brand_boxes = _expand_brand_line(chosen, candidates)
    return brand, class_type, brand_boxes, class_type_boxes


# -------------------------------------------------------------------------------------------------
# ABV & volume logic
# -------------------------------------------------------------------------------------------------
def extract_abv_from_results(
    results: List[Tuple[List[List[float]], str, float]],
    raw_text: str,
    class_type: Optional[str] = None,
) -> tuple[float | None, List[List[List[float]]]]:
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
                return abv_value, [bbox]

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
            # Find the bbox for this value
            for bbox, text, conf in results:
                if extract_abv(text, class_type) == val:
                    return val, [bbox]
            return val, []

    # Fallback: plain-text extraction
    abv_value = extract_abv(raw_text, class_type)
    # For fallback, we don't have a specific bbox, return empty
    return abv_value, []


def extract_net_contents_from_results(
    results: List[Tuple[List[List[float]], str, float]],
    raw_text: str,
) -> tuple[str | None, List[List[List[float]]]]:
    """
    Prefer numbers immediately followed by ml/L/fl oz etc on individual lines.
    If multiple candidates, pick the one with the largest volume.
    Fall back to searching the combined text.
    """
    best: str | None = None
    best_amount = -1

    best_bbox = None
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
            best_bbox = bbox

    if best is not None:
        return best, [best_bbox] if best_bbox else []

    net_contents_value = extract_net_contents(raw_text)
    return net_contents_value, []


# -------------------------------------------------------------------------------------------------
# Shared OCR result processing
# -------------------------------------------------------------------------------------------------
def process_ocr_results(
    results: List[Tuple[List[List[float]], str, float]],
    expected_brand: Optional[str] = None,
    image_width: Optional[int] = None,
    image_height: Optional[int] = None,
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

    # Collect confidences from relevant information searches
    relevant_confs: List[float] = []
    
    # Warning phrases for detection
    warning_phrases = [
        "government warning",
        "surgeon general",
        "during pregnancy",
        "health problems",
        "pregnancy",
        "warning",
    ]
    
    # Collect confidences from results that contribute to relevant information
    for bbox, text, conf in results:
        normalized = text.strip()
        if not normalized:
            continue
        
        lower = normalized.lower()
        
        # Check if this result is a brand candidate (basic checks)
        is_brand_candidate = (
            not looks_like_year(normalized) and
            not normalized.isdigit() and
            not looks_like_volume(normalized) and
            not looks_like_abv_line(normalized) and
            not looks_like_warning(normalized) and
            not _is_digit_dominated(normalized) and
            any(ch.isalpha() for ch in normalized) and
            len(normalized) <= 60
        )
        
        # Check if contains ABV pattern
        has_abv = bool(ABV_PATTERN.search(normalized))
        
        # Check if contains net contents pattern
        has_net_contents = bool(NET_CONTENTS_PATTERN.search(normalized))
        
        # Check if contains warning phrase
        has_warning = any(phrase in lower for phrase in warning_phrases)
        
        # If this result contributes to any relevant information, add its confidence
        if is_brand_candidate or has_abv or has_net_contents or has_warning:
            relevant_confs.append(float(conf))
    
    # Calculate relevant_avg_conf
    if relevant_confs:
        relevant_avg_conf = float(sum(relevant_confs) / len(relevant_confs))
    else:
        relevant_avg_conf = avg_conf

    # Extract structured fields from both layout and combined raw text
    lower_text = raw_text.lower()

    # First guess class_type for ABV sanity checks
    brand, class_type, brand_boxes, class_type_boxes = guess_brand_and_class(results, expected_brand=expected_brand)
    
    # Extract ABV with class_type for sanity checks
    abv, abv_boxes = extract_abv_from_results(results, raw_text, class_type=class_type)
    net_contents, net_contents_boxes = extract_net_contents_from_results(results, raw_text)
    
    # Check for warning phrases and collect warning bboxes
    warning_present = False
    warning_boxes: List[List[List[float]]] = []
    for bbox, text, conf in results:
        lower = text.lower()
        if any(phrase in lower for phrase in warning_phrases):
            warning_present = True
            warning_boxes.append(bbox)

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
        "relevant_avg_conf": relevant_avg_conf,
    }

    # Build field_boxes structure
    field_boxes = {
        "brand": {
            "text": brand,
            "boxes": brand_boxes if brand else [],
        },
        "class_type": {
            "text": class_type,
            "boxes": class_type_boxes if class_type else [],
        },
        "abv": {
            "text": str(abv) if abv is not None else None,
            "boxes": abv_boxes if abv is not None else [],
        },
        "net_contents": {
            "text": net_contents,
            "boxes": net_contents_boxes if net_contents else [],
        },
        "warning": {
            "text": "Warning present" if warning_present else None,
            "boxes": warning_boxes if warning_present else [],
        },
    }
    
    result = {
        "raw_text": raw_text,
        "extracted": extracted,
        "confidence": confidence,
        "field_boxes": field_boxes,
    }
    
    # Add image_size if provided
    if image_width is not None and image_height is not None:
        result["image_size"] = {
            "width": image_width,
            "height": image_height,
        }
    
    return result


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
        image_width, image_height = image.size

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
        return process_ocr_results(results, expected_brand=expected_brand, image_width=image_width, image_height=image_height)


class PaddleOCREngine(LabelAnalysisEngine):
    """
    OCR-based engine using PaddleOCR.
    analyze(image_bytes) -> dict
    """

    async def analyze(self, image_bytes: bytes, **kwargs) -> Dict[str, Any]:
        # Load image from bytes
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image_np = np.array(image)
        image_width, image_height = image.size

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
        return process_ocr_results(results, expected_brand=expected_brand, image_width=image_width, image_height=image_height)


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

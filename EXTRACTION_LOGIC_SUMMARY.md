# Information Extraction Logic Summary

This document provides a concise summary of the logic used to extract desired information from TTB label images.

## Overview

The system uses OCR (Optical Character Recognition) to extract text from label images, then applies specialized algorithms to identify and extract five key fields:
1. **Brand** - The brand name
2. **Class/Type** - Product category (Distilled Spirits, Wine, or Malt Beverages)
3. **ABV** - Alcohol By Volume percentage
4. **Net Contents** - Volume/quantity information
5. **Warning** - Government warning text presence

---

## 1. OCR Engine Selection

The system supports multiple OCR engines:
- **PaddleOCR** (default): Uses angle classification for better text detection
- **EasyOCR**: CPU-only, English language
- **Dummy Engine**: For testing purposes

All engines return normalized results: `[(bbox, text, confidence), ...]` where:
- `bbox`: Bounding box coordinates `[[x1,y1], [x2,y2], [x3,y3], [x4,y4]]`
- `text`: Extracted text string
- `confidence`: OCR confidence score (0.0-1.0)

---

## 2. Brand Detection

### Filtering Phase
Excludes candidates that are:
- Years (4-digit years like 2018, 2020)
- Pure digits
- Volume indicators (e.g., "750ml")
- ABV lines (containing "%" or "alc")
- Warning text
- Digit-dominated text (2+ digits where digits ≥ letters)
- Non-alphabetic text
- Long lines (>60 characters)
- Long body text (20+ chars with small font)

### Selection Phase

**Phase 1: Guided Matching** (if expected brand provided)
- Uses fuzzy matching with `difflib.SequenceMatcher`
- Accepts if similarity > 0.80
- For 0.70-0.80 similarity: Validates by searching for brand name elsewhere on label (including URLs)

**Phase 2: Heuristic Selection** (fallback)
- Relative scoring system with weighted features:
  - **35%** - Size score (bbox height relative to label)
  - **25%** - Density score (fewer characters per area is better)
  - **20%** - Word count (fewer words is better)
  - **10%** - T-shaped spatial preference (top + center vertical position)
  - **10%** - Font distinctiveness (deviation from median font height)
- Tiered search: Top 35% of label → Top 70% → All candidates

### Expansion Phase

**Horizontal Expansion**:
- Joins same-line neighbors
- Left expansion: Accepts short tokens (≤3 chars) and prefix words ("the", "la", "el", etc.)
- Right expansion: Accepts alphabetic tokens (spaces, apostrophes, hyphens allowed)
- Truncates to 5 words if expanded run exceeds limit

**Stacked Suffix Expansion**:
- Finds lines below brand line within 1.2x line height
- Only accepts whitelist phrases:
  - Spirits: "spirits", "distillery", "distilling", etc.
  - Wine: "wine cellars", "vineyards", "winery", etc.
  - Beer: "brewing company", "brewery", "malt beverages", etc.

---

## 3. Class/Type Detection

Uses a **hierarchical keyword scoring system**:

### Scoring Categories
- **Primary identifiers** (3 points each): Strong class indicators
  - Spirits: "spirits", "vodka", "whiskey", "gin", "rum", "tequila", etc.
  - Wine: "wine", "champagne", "cider", "sake", varietal names, etc.
  - Malt Beverages: "beer", "ale", "lager", "stout", "ipa", etc.
- **Contextual indicators** (1 point each): Supporting clues
  - Spirits: "distilled by", "aged", "proof", "bottled in bond", etc.
  - Wine: "vinted by", "vintage", "estate bottled", "contains sulfites", etc.
  - Beer: "brewed by", "hops", "malt", "craft beer", etc.

### Selection Logic
1. Calculate score for each class by summing matching keyword points
2. Return class with highest score
3. Priority for ties: Distilled Spirits > Wine > Malt Beverages
4. Returns `None` if all scores are 0

---

## 4. ABV (Alcohol By Volume) Detection

### Extraction Pattern
Regex: `(\d{1,2}(?:\.\d+)?)\s*%` (e.g., "14.5%", "12%", "40%")

### Three-Tier Strategy

1. **Same-line match**: Prefer ABV values on lines containing both "alc" and ("vol" or "alcohol")
   - If found, return immediately with bbox

2. **Spatial proximity**: If "alc/vol" lines found, select ABV value closest to them
   - Calculates Euclidean distance from each candidate to "alc/vol" line center
   - Returns closest match

3. **Fallback**: Search entire raw text using regex pattern
   - Returns value without specific bbox

### Filtering Logic
- **Grape composition filter**: Excludes percentages followed by varietal keywords (merlot, cabernet, etc.) within 20 characters
- **Wine sanity check**: If ABV > 30% and class_type is "wine", treat as invalid (wine typically < 20%)

---

## 5. Net Contents Detection

### Extraction Pattern
Regex: `(\d{2,4})\s*(ml|mL|ML|l|L|fl\s*oz)`

### Extraction Strategy
1. **Line-by-line search**: Search each OCR result line for pattern
2. **Largest volume selection**: If multiple candidates found, select one with largest numeric value
   - Compares extracted integers
   - Returns full string (number + unit) with bbox
3. **Fallback**: Search entire raw text if no line matches

### Normalization
- `ml`, `mL`, `ML` → "ml" (lowercase)
- `fl oz`, `floz` → "fl oz" (with space)
- `l`, `L` → "l" (lowercase)
- Final format: `"{amount} {unit}"` (e.g., "750 ml", "750 fl oz")

---

## 6. Warning Detection

### Detection Phrases
Searches for (case-insensitive):
- "government warning"
- "surgeon general"
- "during pregnancy"
- "health problems"
- "pregnancy" (standalone)
- "warning" (standalone)

### Detection Logic
- Uses substring search across each OCR result line
- If any phrase found in any line: `warning_present = True`
- Collects all bboxes from lines containing warning phrases
- Warning text is excluded from brand candidate selection

---

## 7. Confidence Gate

### Relevant Average Confidence
Calculates `relevant_avg_conf` from OCR tokens that contribute to relevant fields:
- Brand candidates (passed filtering)
- ABV lines (containing ABV pattern)
- Net contents lines (containing volume pattern)
- Warning lines (containing warning phrases)

### Gate Behavior
- If `relevant_avg_conf < 0.60`: 
  - Returns "review" for all fields
  - Note: "Unable to verify with given image. Please check image quality."
  - Bypasses normal verification logic

---

## 8. Verification/Comparison Logic

### Brand Verification
1. **Exact match**: Normalize both strings (lowercase, strip whitespace) → **PASS** if equal
2. **Enhanced matching** (if exact match fails):
   - Character count equality (ignoring whitespace and punctuation)
   - 75% substring similarity (using `difflib.SequenceMatcher`)
   - Form submission appears in label text
   - If all 3 conditions met: **PASS** with note "Matched with enhanced validation"

### Class/Type Verification
- Normalize both strings (lowercase, strip whitespace)
- **PASS** if exact match
- **FAIL** if mismatch
- **REVIEW** if not detected

### ABV Verification
- **N/A handling**: If form value is "n/a":
  - No ABV detected: **PASS** ("Not detected")
  - ABV detected: **REVIEW** ("User claimed N/A but value detected")
- **Tolerance**: Values must be within 0.5% to pass
- **Not detected**: **REVIEW** ("Not detected")
- **Parse failure**: **REVIEW** ("Could not parse ABV value")

### Net Contents Verification
- **N/A handling**: If form value is "n/a":
  - No net contents detected: **PASS** ("Not detected")
  - Net contents detected: **REVIEW** ("User claimed N/A but value detected")
- **Numeric comparison**: Extract integers from both form and label, compare
- **Not detected**: **REVIEW** ("Not detected")
- **Parse failure**: **REVIEW** ("Could not extract numeric value")

### Warning Verification
- **Mandatory field**: Warning must be present
- **Not detected**: If label has no warning: **REVIEW** ("Not detected")
- **Warning missing**: If OCR detects no warning OR form claims no warning: **FAIL** ("Labels must have warning")
- **Warning present**: If OCR detects warning:
  - Form also claims warning: **PASS**
  - Form does not claim warning: **FAIL**
- **User claims but OCR misses**: **REVIEW** ("Warning claimed but not detected by OCR - manual verification recommended")

### Overall Status Determination

**Mandatory fields**: `["brand", "class_type", "abv", "net_contents", "warning"]`

**Special Warning Check**:
- Warning is mandatory - if missing (unchecked in form OR not detected by OCR), overall status = **FAIL** regardless of other field results

**Standard Status Logic** (if warning is present):
- **FAIL**: If any mandatory field has "fail"
- **PASS**: If all mandatory fields have "pass"
- **REVIEW**: Otherwise (some fields are "review" or missing)

---

## Key Features

1. **Spatial Awareness**: Uses bounding box positions for contextual matching
2. **Multi-Tier Fallbacks**: Tries contextual matches before simple text search
3. **Confidence-Based Quality Control**: Low confidence triggers review mode
4. **Normalization**: Handles case, whitespace, and punctuation variations
5. **Special Case Handling**: Cursive text, long brand names, N/A values

---

## Output Structure

The OCR processing returns:
- `raw_text`: Combined text from all OCR results
- `extracted`: Dictionary with brand, abv, class_type, net_contents, warning_present
- `confidence`: avg_conf, min_conf, num_tokens, relevant_avg_conf
- `field_boxes`: Bounding box information for each detected field
- `image_size`: Width and height (if provided)

---

*For detailed implementation, see `ocr_logic.md` and `backend/app/services/label_engine/ocr_local.py`*


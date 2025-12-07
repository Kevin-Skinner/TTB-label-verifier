# OCR Logic Documentation

This document describes all the logic used to determine information from label images in the TTB Label Verifier system. This file should be updated whenever OCR logic is added, modified, or removed.

## Table of Contents

1. [OCR Engine Selection](#ocr-engine-selection)
2. [Brand Detection](#brand-detection)
3. [Class/Type Detection](#classtype-detection)
4. [ABV (Alcohol By Volume) Detection](#abv-alcohol-by-volume-detection)
5. [Net Contents Detection](#net-contents-detection)
6. [Warning Detection](#warning-detection)
7. [Verification/Comparison Logic](#verificationcomparison-logic)
8. [Confidence Metrics](#confidence-metrics)

---

## OCR Engine Selection

The system supports multiple OCR engines and selects one based on environment variables:

- **PaddleOCR** (default): Used when `OCR_ENGINE=paddleocr` or not specified
  - Uses `use_angle_cls=True` for better text angle detection
  - Handles multiple PaddleOCR output formats (parallel lists format and legacy formats)
  - Requires `KMP_DUPLICATE_LIB_OK=TRUE` environment variable for OpenMP compatibility
- **EasyOCR**: Used when `OCR_ENGINE=easyocr`
  - CPU-only, English language
  - Lazy initialization (singleton pattern)
- **Dummy Engine**: Used when `USE_DUMMY_ENGINE=true` (for testing)
  - Returns empty results with zero confidence

All engines return normalized results in the format: `List[Tuple[bbox, text, confidence]]` where:
- `bbox`: Bounding box coordinates `[[x1,y1], [x2,y2], [x3,y3], [x4,y4]]`
- `text`: Extracted text string
- `confidence`: OCR confidence score (0.0-1.0)

### Expected Brand Parameter

The `analyze()` method accepts an optional `expected_brand` parameter:
- When provided, brand detection uses guided matching (see [Brand Detection - Phase 1](#phase-1-guided-matching-if-expected-brand-provided))
- Improves accuracy when the brand name is known in advance
- Used by the verification endpoint when form submission includes brand name

---

## Brand Detection

### Candidate Filtering

The system filters OCR results to identify potential brand names by excluding:

1. **Years**: 4-digit years matching pattern `^(19|20)\d{2}$` (e.g., 2018, 2020)
2. **Pure digits**: Lines containing only numeric characters
3. **Volume indicators**: Lines matching net contents pattern (e.g., "750ml", "750 ml")
4. **ABV lines**: Lines containing "%" or "alc"
5. **Warning text**: Lines containing "government warning", "warning", or "pregnancy"
6. **Digit-dominated text**: Lines with 2+ digits where digits ≥ letters
7. **Non-alphabetic**: Lines with no alphabetic characters
8. **Long lines**: Lines exceeding 60 characters
9. **Long body text**: Lines with 20+ characters where font height < 1.2x median height (to filter out paragraph text)

### Candidate Selection

After filtering, candidates are scored and selected using a multi-phase approach:

#### Phase 1: Guided Matching (if expected brand provided)

When an expected brand name is provided:

1. **Fuzzy matching**: Calculate similarity ratio using `difflib.SequenceMatcher` for each candidate
2. **Long brand priority**: If expected brand is 20+ characters, boost priority for candidates matching ≥80% of expected length
3. **High confidence match**: If similarity ratio > 0.80, accept immediately
4. **Imperfect match validation** (0.70-0.80 ratio):
   - Search raw text for brand name or slugified version (e.g., "theprisoner" for "The Prisoner")
   - Check for brand in URLs (e.g., "theprisonerwine.com")
   - If found elsewhere in label, accept the imperfect fuzzy match

#### Phase 2: Heuristic Selection with Relative Scoring (fallback)

If no expected brand or guided matching fails, candidates are scored using a relative scoring system:

1. **Feature calculation** (normalized relative to label distribution):
   - **size_score** (35% weight): Relative bbox height
   - **density_score** (25% weight): Lower character density is better (fewer chars per area)
   - **words_score** (20% weight): Fewer words is better
   - **T_score** (10% weight): T-shaped spatial preference (top + center vertical)
   - **distinct_score** (10% weight): Font height distinctiveness from median

2. **Tiered T-search**:
   - **Tier 1**: Top 35% of label (y_norm ≤ 0.35)
   - **Tier 2**: Top 70% of label (y_norm ≤ 0.70)
   - **Fallback**: All candidates if tiers are empty
   - Selection order: Try Tier 1 first, then Tier 2, then fallback

3. **Final selection**: Candidate with highest `brand_score` from active tier

### Brand Line Expansion

After selecting the anchor candidate, the system expands it to include related text using a two-phase approach:

#### Phase 1: Horizontal Expansion (Same-Line Neighbors)

The system finds and joins text on the same line as the anchor:

1. **Neighbor detection**: Find candidates with:
   - Similar height (0.8x to 1.2x anchor height)
   - Same line (vertical offset < 0.3x anchor height)
   
2. **Left expansion**: Expand leftward accepting:
   - Short tokens (≤3 characters)
   - Prefix whitelist words: "la", "el", "los", "las", "the", "le", "de", "di", "da", "do"
   - Maximum horizontal gap: 1.0x anchor height
   
3. **Right expansion**: Expand rightward accepting:
   - Alphabetic tokens (allowing spaces, apostrophes, hyphens)
   - Maximum length: 16 characters per token
   - Maximum horizontal gap: 1.0x anchor height

4. **Truncation**: If expanded run exceeds 5 words, keep anchor centered and truncate to 5 words

#### Phase 2: Stacked Suffix Expansion (Lines Below)

The system finds and appends suffix lines below the brand line:

1. **Stacked line detection**: Find candidates that are:
   - Below the brand line (vertical gap > 0)
   - Within 1.2x line height below
   - Similar height (0.7x to 1.3x line height)
   - Horizontally centered (within 1.0x line height from center)

2. **Suffix whitelist**: Only accept lines matching:
   - "spirits", "distillery", "distilling", "distilling co", "distilling company"
   - "wine cellars", "cellars", "vineyards", "vineyard", "winery"
   - "brewing company", "brewery", "brewing", "malt beverages", "beer", "ale"
   - Exact match or starts with whitelist phrase

3. **Result**: Join horizontally-expanded line with stacked suffix lines (e.g., "STAG'S LEAP" + "WINE CELLARS" → "STAG'S LEAP WINE CELLARS")

### Special Cases

- **"The Prisoner" Fix**: Handles cursive OCR errors by checking for brand name in URLs/raw text when fuzzy match is 0.70-0.80
- **"The Associated Vintners" Fix**: Handles long brand names (up to 60 chars) by checking font height to distinguish headers from body text

---

## Class/Type Detection

Class/type is determined using a **hierarchical keyword scoring system** that outputs one of the canonical class strings:

- "Distilled Spirits"
- "Wine"
- "Malt Beverages"
- `None` (if classification is not confident)

### Scoring System

The system uses weighted keyword matching with three categories per class:

1. **Primary identifiers** (3 points each): Strong class indicators
2. **Varietals** (for wine only, 3 points each): Grape varietal names
3. **Contextual indicators** (1 point each): Supporting context clues

### Keyword Sets

#### Distilled Spirits

**Primary identifiers** (3 points):
- "spirits", "distilled spirits", "neutral spirits", "grain spirits"
- "vodka", "whisky", "whiskey", "bourbon", "rye", "scotch"
- "gin", "brandy", "cognac", "armagnac", "rum", "rhum"
- "cachaça", "cachaca", "tequila", "mezcal", "agave spirit"
- "sotol", "liqueur", "cordial", "absinthe", "akvavit", "aquavit"
- "arrack", "kirsch", "kirschwasser", "slivovitz", "grappa"
- "pisco", "calvados", "applejack", "bitters"
- "moonshine", "schnapps", "genever"
- "shochu", "baijiu", "soju"

**Contextual indicators** (1 point):
- "distilled by", "blended by", "single malt", "single barrel"
- "small batch", "cask strength", "proof"
- "aged", "non-chill filtered"
- "bottled in bond", "reposado", "añejo", "anejo", "blanco"
- "v.s.", "v.s.o.p.", "x.o."

**Special handling**: "alcohol" by itself (without "%" or "by volume") counts as 1 point for spirits.

#### Wine

**Primary identifiers** (3 points):
- "wine", "table wine", "dessert wine", "sparkling wine"
- "champagne", "carbonated wine", "vermouth"
- "cider", "hard cider", "perry"
- "mead", "honey wine", "sake"
- "sherry", "port", "porto", "madeira", "marsala"
- "tokay", "tokaji", "retsina", "aperitif wine"
- "sangria", "mistelle"

**Varietals** (3 points each):
- "cabernet sauvignon", "chardonnay", "merlot"
- "pinot noir", "pinot grigio", "pinot gris"
- "sauvignon blanc", "riesling", "zinfandel"
- "syrah", "shiraz", "malbec", "grenache", "garnacha"
- "tempranillo", "sangiovese"
- "moscato", "muscat"
- "rose", "rosé", "prosecco", "cava", "lambrusco"

**Contextual indicators** (1 point):
- "vinted by", "cellared by", "vintage", "estate bottled"
- "grown, produced, and bottled by"
- "appellation", "ava"
- "contains sulfites"
- "sec", "demi-sec", "brut", "extra dry"
- "cuvée", "cuvee"
- "late harvest", "ice wine", "eiswein"
- "sur lie", "old vine"

#### Malt Beverages (Beer)

**Primary identifiers** (3 points):
- "malt beverage", "beer", "ale", "lager"
- "stout", "porter", "pilsner", "pilsener"
- "bock", "doppelbock"
- "hefeweizen", "weizen", "wheat beer"
- "kolsch", "kölsch"
- "saison", "gose", "lambic"
- "barleywine", "malt liquor"
- "hard seltzer"
- "root beer" (when clearly alcoholic)

**Contextual indicators** (1 point):
- "brewed by", "brewing company", "brewery"
- "ipa", "india pale ale", "double ipa", "dipa"
- "hops", "hopped", "dry hopped"
- "malt", "malted"
- "ibu", "draft", "draught"
- "craft beer", "microbrew"
- "imperial", "session", "nitro"
- "tripel", "dubbel", "quadrupel"
- "sour" (as a beer style)

### Selection Logic

1. **Score calculation**: For each class, sum points from matching keywords
   - Each matching keyword adds its weight (3 for primary/varietals, 1 for contextual)
   - Bounding boxes from OCR results containing matching keywords are collected
2. **Priority**: Distilled Spirits > Wine > Malt Beverages (for ties)
3. **Result**: 
   - If all scores are 0: return `None` with empty bbox list
   - Otherwise: return the class with highest score
   - If tied: use priority order (Spirits > Wine > Malt)
   - Returns class string and list of bboxes from contributing OCR results

### Text Normalization

- All matching is case-insensitive
- Punctuation is normalized (removed/replaced with spaces)
- Multiple spaces are collapsed to single spaces

---

## ABV (Alcohol By Volume) Detection

### Extraction Pattern

ABV is extracted using regex pattern: `(\d{1,2}(?:\.\d+)?)\s*%`

Examples: "14.5%", "12%", "40%"

### Extraction Strategy

The system uses a three-tier approach:

1. **Same-line match**: Prefer ABV values on lines containing both "alc" and ("vol" or "alcohol")
   - If found, return immediately with the bbox from that line
   
2. **Spatial proximity**: If "alc/vol" lines found, select ABV value closest to them (by Euclidean distance)
   - For each "alc/vol" line, find all ABV candidates in results
   - Calculate Euclidean distance from each candidate to the "alc/vol" line center
   - Return the closest ABV value with its bbox
   
3. **Fallback**: Search entire raw text using regex pattern
   - If no spatial matches found, extract from combined raw text
   - Returns value without specific bbox

### Filtering Logic

To avoid false positives, ABV extraction filters out:

1. **Grape composition percentages**: If percentage is followed by varietal keywords within 20 characters:
   - Keywords: merlot, cabernet, shiraz, pinot, grape, blend, vintage, chardonnay, sauvignon, riesling, zinfandel, malbec, syrah
   - Checks text after the percentage match (next 20 characters)

2. **Sanity check for wine**: If ABV > 30% and class_type is "wine", treat as invalid (wine typically < 20%)
   - Applied during extraction if class_type is known

### Comparison Logic

When comparing form submission to detected ABV:

- **N/A handling**: If form value is "n/a" (case-insensitive):
  - If label has no ABV: **PASS** with note "Not detected"
  - If label has ABV: **REVIEW** with note "User claimed N/A but value detected"
- **Tolerance**: Values must be within 0.5% to pass (e.g., 14.0% matches 14.5%)
- **Not detected**: If label has no ABV: **REVIEW** with note "Not detected"
- **Parse failure**: If form value cannot be converted to float: **REVIEW** with note "Could not parse ABV value"

---

## Net Contents Detection

### Extraction Pattern

Net contents are extracted using regex pattern: `(\d{2,4})\s*(ml|mL|ML|l|L|fl\s*oz)`

Examples: "750ml", "750 ml", "1.5L", "750 fl oz"

### Extraction Strategy

1. **Line-by-line search**: Search each OCR result line for net contents pattern
2. **Largest volume selection**: If multiple candidates found, select the one with largest numeric value
   - Extracts numeric portion (2-4 digits) from each candidate
   - Compares as integers to find maximum
   - Returns the full string (number + unit) of the largest value
   - Includes the bbox from the selected line
3. **Fallback**: Search entire raw text if no line matches
   - Returns value without specific bbox

### Normalization

Units are normalized during extraction:
- `ml`, `mL`, `ML` → "ml" (normalized to lowercase, spaces removed)
- `fl oz`, `floz` → "fl oz" (normalized with space)
- `l`, `L` → "l" (normalized to lowercase)
- Final format: `"{amount} {unit}"` (e.g., "750 ml", "750 fl oz", "750 l")

### Comparison Logic

When comparing form submission to detected net contents:

- **N/A handling**: If form value is "n/a" (case-insensitive):
  - If label has no net contents: **PASS** with note "Not detected"
  - If label has net contents: **REVIEW** with note "User claimed N/A but value detected"
- **Numeric comparison**: Extract numeric values from both form and label, compare integers
  - Uses regex `\d+` to find first sequence of digits
  - Compares extracted integers
- **Not detected**: If label has no net contents: **REVIEW** with note "Not detected"
- **Parse failure**: If numeric value cannot be extracted from either form or label: **REVIEW** with note "Could not extract numeric value"

---

## Warning Detection

### Detection Phrases

The system searches for the following phrases in the raw OCR text (case-insensitive):

1. "government warning"
2. "surgeon general"
3. "during pregnancy"
4. "health problems"
5. "pregnancy" (standalone)
6. "warning" (standalone)

### Detection Logic

- **Phrase matching**: Uses substring search across each OCR result line
- **Any match**: If any phrase is found in any line, `warning_present = True`
- **Bounding boxes**: All bboxes from lines containing warning phrases are collected
- **Filtering**: Lines containing warning text are excluded from brand candidate selection

### Comparison Logic

When comparing form submission to detected warning:

- **Not detected**: If label has no warning (`label_value is None`): **REVIEW** with note "Not detected"
- **Warning missing**: If OCR detects no warning (`label_value is False`) OR form claims no warning (`form_value is False`): **FAIL** with note "Labels must have warning"
- **Warning present**: If OCR detects warning (`label_value is True`):
  - If form also claims warning (`form_value is True`): **PASS**
  - If form does not claim warning (`form_value is False`): **FAIL**
- **User claims warning but OCR misses it**: If OCR detects no warning (`label_value is False`) but user claims warning (`form_value is True`): **REVIEW** with note "Warning claimed but not detected by OCR - manual verification recommended"

---

## Verification/Comparison Logic

### Brand Verification

Brand verification uses enhanced matching logic when initial exact match fails:

#### Exact Match
- Normalize both strings (lowercase, strip whitespace)
- If equal: **PASS**

#### Enhanced Matching (if exact match fails)

Three conditions must ALL be met:

1. **Character count equality**: 
   - Count non-whitespace characters (case-insensitive, spaces removed)
   - Uses regex `\s` to remove all whitespace, then compares lengths
   - Must be equal between form and label

2. **75% substring match**:
   - Calculate similarity ratio using `difflib.SequenceMatcher`
   - Must be ≥ 0.75

3. **Form submission appears in label**:
   - Search raw text for form submission (case-insensitive)
   - Try variations: original, normalized, no-spaces version
   - Must be found

**If all 3 conditions met**:
- Extract matching string from raw text (preserving original case)
- Return **PASS** with note "Matched with enhanced validation"
- Return the matched string as the label value

**If any condition fails**: **FAIL**

### Class/Type Verification

- Normalize both strings (lowercase, strip whitespace)
- Exact match: **PASS**
- Mismatch: **FAIL**
- Not detected: **REVIEW** with note "Not detected"

### ABV Verification

See [ABV Comparison Logic](#comparison-logic) above.

### Net Contents Verification

See [Net Contents Comparison Logic](#comparison-logic-1) above.

### Warning Verification

See [Warning Comparison Logic](#comparison-logic-2) above.

### Overall Status Determination

The overall verification status is determined by mandatory fields:

**Mandatory fields**: `["brand", "class_type", "abv", "net_contents", "warning"]`

**Special Warning Check**:
- **Warning is mandatory**: If warning is not present (form unchecked OR OCR doesn't detect it), the overall status is **FAIL** regardless of other field results
- The warning field check is updated to "fail" with note "Labels must have warning" when missing
- This check happens before evaluating other mandatory fields

**Standard Status Logic** (if warning is present):
- **FAIL**: If any mandatory field has "fail"
- **PASS**: If all mandatory fields have "pass"
- **REVIEW**: Otherwise (some fields are "review" or missing)

**Note**: Warning is mandatory - if warning is missing (unchecked in form or not detected by OCR), the overall status will be "fail" even if all other fields match correctly.

---

## Helper Functions

### String Normalization

- `normalize_string(value)`: Lowercase and strip whitespace
- `_slugify_brand(brand)`: Convert to URL-friendly format (lowercase, no spaces/punctuation)
  - Removes all non-word characters using regex `[^\w]`
  - Used for searching brand names in URLs (e.g., "theprisoner" for "The Prisoner")

### Bounding Box Utilities

- `_bbox_stats(bbox)`: Returns `(top_y, height, width)` for a bounding box
  - `top_y`: Minimum y coordinate (topmost point)
  - `height`: Difference between max and min y coordinates
  - `width`: Difference between max and min x coordinates
- `_bbox_center(bbox)`: Returns `(center_x, center_y)` for a bounding box
- `_bbox_left(bbox)`: Returns leftmost x coordinate
- `_bbox_right(bbox)`: Returns rightmost x coordinate
- `_bbox_top(bbox)`: Returns topmost y coordinate
- `_bbox_bottom(bbox)`: Returns bottommost y coordinate

### Text Classification

- `looks_like_year(text)`: Checks if text is a 4-digit year (19xx or 20xx)
  - Pattern: `^(19|20)\d{2}$`
- `looks_like_volume(text)`: Checks if text matches net contents pattern
  - Uses `NET_CONTENTS_PATTERN` regex
- `looks_like_abv_line(text)`: Checks if text contains "%" or "alc" (case-insensitive)
- `looks_like_warning(text)`: Checks if text contains warning keywords
  - Searches for: "government warning", "warning", or "pregnancy" (case-insensitive)
- `_is_digit_dominated(text)`: Checks if text has 2+ digits and digits ≥ letters
  - Counts alphabetic and numeric characters separately
  - Returns True if digits ≥ 2 and digits ≥ letters

### Extraction Functions

- `extract_abv(text, class_type)`: Extracts ABV value from text string
  - Returns float or None
  - Applies grape composition filtering and wine sanity checks
- `extract_net_contents(text)`: Extracts net contents from text string
  - Returns formatted string (e.g., "750 ml") or None
  - Normalizes units during extraction

---

## Output Structure

The OCR processing returns a structured dictionary with the following fields:

### Raw Text

- `raw_text`: Combined text from all OCR results, joined with spaces
  - Used for fallback extraction and brand verification
  - Preserves original case for matching

### Extracted Fields

- `brand`: Detected brand name (string or None)
- `abv`: Detected ABV value (float or None)
- `class_type`: Detected class/type (string or None: "Distilled Spirits", "Wine", "Malt Beverages")
- `net_contents`: Detected net contents (string or None, e.g., "750 ml")
- `warning_present`: Boolean indicating if warning was detected

### Confidence Metrics

- `avg_conf`: Average confidence across all OCR tokens
- `min_conf`: Minimum confidence across all OCR tokens
- `num_tokens`: Total number of OCR tokens detected
- `relevant_avg_conf`: Average confidence of tokens contributing to relevant fields

### Field Boxes

The `field_boxes` structure contains bounding box information for each detected field:

```python
{
    "brand": {
        "text": "BRAND NAME",
        "boxes": [[[x1,y1], [x2,y2], [x3,y3], [x4,y4]], ...]  # List of bboxes
    },
    "class_type": {
        "text": "Wine",
        "boxes": [[[x1,y1], [x2,y2], [x3,y3], [x4,y4]], ...]
    },
    "abv": {
        "text": "14.5",
        "boxes": [[[x1,y1], [x2,y2], [x3,y3], [x4,y4]], ...]
    },
    "net_contents": {
        "text": "750 ml",
        "boxes": [[[x1,y1], [x2,y2], [x3,y3], [x4,y4]], ...]
    },
    "warning": {
        "text": "Warning present" or None,
        "boxes": [[[x1,y1], [x2,y2], [x3,y3], [x4,y4]], ...]
    }
}
```

- **Brand boxes**: May include multiple bboxes from horizontal expansion and stacked suffix lines
- **Class type boxes**: Bboxes from OCR results containing class/type keywords
- **ABV boxes**: Bbox from the line containing ABV (or empty if fallback extraction)
- **Net contents boxes**: Bbox from the line with largest volume (or empty if fallback)
- **Warning boxes**: All bboxes from lines containing warning phrases

### Image Size

- `image_size`: Dictionary with `width` and `height` (if provided to `process_ocr_results`)

## Confidence Metrics

### Relevant Average Confidence

The system calculates `relevant_avg_conf` - the average confidence of OCR tokens that contributed to relevant information extraction:

The system collects confidences from OCR results that contribute to any relevant field:

1. **Brand candidates**: OCR results that passed brand candidate filtering
   - Not a year, not pure digits, not volume/ABV/warning
   - Has alphabetic characters, length ≤ 60
   - For long lines (20+ chars): font height ≥ 1.2x median

2. **ABV lines**: Lines containing ABV pattern matches (`(\d{1,2}(?:\.\d+)?)\s*%`)

3. **Net contents lines**: Lines containing net contents pattern matches (`(\d{2,4})\s*(ml|mL|ML|l|L|fl\s*oz)`)

4. **Warning lines**: Lines containing any warning phrase
   - "government warning", "surgeon general", "during pregnancy", "health problems", "pregnancy", "warning"

If no relevant confidences are found, `relevant_avg_conf` falls back to overall `avg_conf`.

### Confidence Gate Behavior

If `relevant_avg_conf < 0.60`, the system returns "review" for all fields with note "Unable to verify with given image. Please check image quality." This prevents verification attempts when OCR quality is too low.

When confidence gate is triggered:
- All five fields (brand, class_type, abv, net_contents, warning) return result "review"
- Each field's `label_value` is `None`
- Each field's notes: "Unable to verify with given image. Please check image quality."
- Overall status: "review"
- Normal verification logic is bypassed
- `field_boxes` structure is still included (may be empty)

## Notes

- All string comparisons are case-insensitive
- OCR confidence scores are used in the confidence gate decision
- The system prioritizes spatial and contextual clues over simple text matching
- Special handling exists for edge cases like cursive text, long brand names, and N/A values
- **Warning is mandatory**: Labels must have a warning present. If warning is missing (unchecked in form or not detected by OCR), overall status will be "fail" with note "Labels must have warning"
- Brand comparison uses enhanced matching with character count equality (ignoring whitespace and punctuation) and similarity checks
- ABV and Net Contents support "n/a" values when not applicable

---

*Last Updated: December 2024*
*This document should be updated whenever OCR logic changes.*


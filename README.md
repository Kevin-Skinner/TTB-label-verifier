# TTB Label Verifier

A web application for verifying TTB (Alcohol and Tobacco Tax and Trade Bureau) alcohol beverage labels against regulatory requirements using OCR (Optical Character Recognition) technology.

> **Note:** the hosted demo has been retired. This repository is preserved as a portfolio/reference implementation — clone and run locally per the instructions below.

## What It Does

The TTB Label Verifier automatically extracts and verifies key information from alcohol beverage label images:

- **Brand Name**: Detects and verifies the product brand
- **Class/Type**: Identifies product category (Distilled Spirits, Wine, or Malt Beverages)
- **ABV (Alcohol By Volume)**: Extracts and validates alcohol percentage
- **Net Contents**: Detects volume/quantity information
- **Government Warning**: Verifies presence of required warning text

The application uses **PaddleOCR** for text extraction and applies specialized algorithms to identify and verify each field. It's designed to handle noisy, real-world images rather than requiring high-quality scans.

For detailed information on how fields are extracted, see [EXTRACTION_LOGIC_SUMMARY.md](./EXTRACTION_LOGIC_SUMMARY.md).

## How to Use

1. **Upload a label image** (JPG, PNG, or other image format)
2. **Enter the expected information** in the form:
   - Brand name
   - Class/Type (dropdown selection)
   - ABV (percentage or decimal, or N/A)
   - Net Contents (with unit selection, or N/A)
   - Warning Present (checkbox)
3. **Click "Verify Label"** to process the image
4. **Review the results** showing:
   - Verification status for each field (PASS/FAIL/REVIEW)
   - Detected values from OCR
   - Visual overlay showing where information was extracted
   - Overall verification status

### Verification Status

- **PASS**: Field matches between form and OCR detection
- **FAIL**: Field mismatch or missing required information (e.g., warning)
- **REVIEW**: Requires manual verification (low OCR confidence, not detected, or user claimed N/A but value detected)

**Important**: Government warning is mandatory. If warning is not present (unchecked in form or not detected by OCR), overall status will be **FAIL** regardless of other field matches.

## Getting Started

### Prerequisites

- Docker and Docker Compose (recommended), OR
- Python 3.10+ and pip

### Option 1: Docker (Recommended)

```bash
# Clone the repository
git clone <repository-url>
cd TTB-label-verifier

# Start the application
docker-compose up --build
```

The application will be available at `http://localhost:8000`

**Stop the application:**
```bash
docker-compose down
```

### Option 2: Local Development

```bash
# Navigate to backend directory
cd backend

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn app.main:app --reload
```

The application will be available at `http://localhost:8000`

**Note**: The frontend is served directly by the FastAPI backend. No separate frontend server is needed.

### Environment Variables

Optional configuration via environment variables:

- `OCR_ENGINE`: Set to `"paddleocr"` (default) or `"easyocr"`
- `USE_DUMMY_ENGINE`: Set to `"true"` for faster testing without OCR processing

Example:
```bash
OCR_ENGINE=easyocr docker-compose up
```

## Extraction Logic

The application uses sophisticated algorithms to extract information from label images:

- **Brand Detection**: Multi-phase approach using fuzzy matching, spatial scoring, and horizontal/stacked expansion
- **Class/Type Detection**: Hierarchical keyword scoring system (primary identifiers + contextual indicators)
- **ABV Detection**: Three-tier strategy (same-line match → spatial proximity → regex fallback)
- **Net Contents Detection**: Pattern matching with largest volume selection
- **Warning Detection**: Phrase matching across OCR results

The system includes a **confidence gate** that returns "REVIEW" status when OCR confidence is too low (< 0.60), ensuring quality control.

For complete details on extraction algorithms and verification logic, see [EXTRACTION_LOGIC_SUMMARY.md](./EXTRACTION_LOGIC_SUMMARY.md).

## Design Decisions

Key technology choices and architectural decisions:

- **OCR Engine**: PaddleOCR selected for superior accuracy and robustness
- **Frontend**: HTMX (instead of React) for enhanced security
- **Backend**: FastAPI for high-performance async operations
- **Modularity**: Built with engine swapping in mind for future model evaluation

For detailed rationale and technical architecture, see [DESIGN_DECISIONS.md](./DESIGN_DECISIONS.md).

## Project Structure

```
TTB-label-verifier/
├── backend/          # FastAPI backend application
│   ├── app/
│   │   ├── api/      # API routes
│   │   └── services/ # OCR and verification logic
│   └── requirements.txt
├── frontend/         # HTMX frontend
│   ├── index.html    # Main HTML
│   └── static/       # CSS and JavaScript
├── docker-compose.yml
└── Dockerfile
```

## Documentation

- [EXTRACTION_LOGIC_SUMMARY.md](./EXTRACTION_LOGIC_SUMMARY.md) - Detailed field extraction algorithms
- [DESIGN_DECISIONS.md](./DESIGN_DECISIONS.md) - Technology choices and architecture
- [ocr_logic.md](./ocr_logic.md) - Complete OCR logic documentation

## License

MIT

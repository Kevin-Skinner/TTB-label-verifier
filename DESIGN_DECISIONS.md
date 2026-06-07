# Design Decisions and Technical Architecture

This document outlines the key design decisions, technology choices, and architectural considerations for the TTB Label Verifier application. It is intended to provide reviewers with comprehensive context on the system's design rationale and implementation approach.

---

## Table of Contents

1. [OCR Model Selection](#ocr-model-selection)
2. [Application Design](#application-design)
3. [Optional Features](#optional-features)
4. [Implementation Details](#implementation-details)
5. [Future Considerations](#future-considerations)

---

## OCR Model Selection

### Primary Choice: PaddleOCR

**Selected Model**: PaddleOCR (default)

**Rationale**: PaddleOCR was chosen as the primary OCR engine based on superior accuracy and robustness compared to other production-ready OCR models, specifically:

- **Higher accuracy** in text recognition across various image qualities
- **Better robustness** to image quality variations and transformations
- **Superior performance** with noisy, real-world images

### Comparison with Alternatives

#### EasyOCR
- **Status**: Implemented as alternative option
- **Configuration**: Available via `OCR_ENGINE=easyocr` environment variable
- **Characteristics**: CPU-only, English language support
- **Use Case**: Can be used for comparison testing or as fallback

#### Tesseract
- **Status**: Considered but not implemented
- **Rationale**: Lower accuracy and robustness compared to PaddleOCR for this use case

#### Ovis2-8B (Future Consideration)
- **Status**: Not currently implemented
- **Rationale**: Recent benchmarking papers indicate superior recognition and parsing performance
- **Future Application**: Would be considered for dedicated on-site hardware deployments
- **Note**: Requires more computational resources, making it suitable for specialized hardware rather than cloud/third-party hosting

### Image Quality Considerations

**Design Philosophy**: The application is designed to handle noisy, real-world images rather than requiring high-quality scans.

**Input Expectations**:
- **Ideal**: Scanned images of labels from applicant companies
- **Reality**: Noisy images from various sources (photographs, low-quality scans, etc.)
- **Design Goal**: Robust performance across image quality spectrum

**Implementation**: PaddleOCR is configured with:
- `use_angle_cls=True` for better text angle detection
- Handles multiple output formats (parallel lists and legacy formats)
- Requires `KMP_DUMMY_LIB_OK=TRUE` environment variable for OpenMP compatibility

### Modularity and Extensibility

**Architecture**: The codebase is built with modularity in mind to allow for easy model swapping.

**Implementation Details**:
- Abstract base class `LabelAnalysisEngine` defines the interface
- Factory pattern (`get_label_engine()`) selects engine based on environment variables
- All engines return normalized results: `List[Tuple[bbox, text, confidence]]`
- Lazy initialization pattern for OCR readers (singleton)

**Configuration**:
```python
# Environment variables control engine selection
OCR_ENGINE=paddleocr  # Options: "paddleocr" (default), "easyocr"
USE_DUMMY_ENGINE=false  # For testing without OCR processing
```

**Future Enhancement**: An automated pipeline could be built to evaluate different model performances and select the best model for the specific task, leveraging the modular architecture.

---

## Application Design

### Frontend Framework: HTMX over React

**Selected Technology**: HTMX (Hypermedia)

**Rationale**: React was avoided due to security concerns:
- **Security Risk**: Recent vulnerability exploits in React architecture allow attackers to remotely execute code on server hardware
- **Mitigation Strategy**: HTMX provides a more secure alternative for dynamic web interactions
- **Deployment Context**: This design mitigates security risks for both third-party cloud hosting and on-site deployments

**HTMX Implementation**:
- Loaded from CDN: `https://unpkg.com/htmx.org@1.9.10`
- Used for form submissions and dynamic content updates
- Attributes: `hx-post`, `hx-swap`, `hx-indicator`, `hx-on::after-request`
- Complements vanilla JavaScript for client-side interactions

**Architecture Benefits**:
- Server-driven approach reduces client-side attack surface
- Simpler deployment (no build step required)
- Direct HTML manipulation reduces XSS risks
- Better suited for on-premises deployments with security requirements

### Backend Framework: FastAPI

**Selected Technology**: FastAPI (Python)

**Rationale**:
- High performance async framework
- Automatic API documentation
- Type safety with Pydantic models
- Easy integration with OCR libraries (PaddleOCR, EasyOCR)

**Deployment**:
- Designed to support both third-party cloud hosting and on-site deployment
- Docker containerization for consistent deployment

### Security Considerations

**Design Principles**:
1. **Minimal Client-Side Code**: HTMX reduces attack surface compared to React SPA
2. **Server-Side Validation**: All verification logic runs server-side
3. **Modular Architecture**: Easy to audit and secure individual components
4. **Environment-Based Configuration**: Sensitive settings via environment variables

**On-Site Hosting Readiness**:
- The application architecture is designed with on-site deployment in mind
- Security-first approach reduces risks for sensitive government/compliance applications
- No reliance on external CDNs for critical functionality (HTMX can be self-hosted)

---

## Optional Features

### Box Highlight Visualization

**Feature**: Visual overlay showing where OCR model extracts information from the label image.

**Current Status**: Proof-of-concept implementation

**Implementation Details**:
- Canvas-based rendering of label image
- SVG overlay for bounding boxes
- Color-coded fields:
  - Brand: Orange (`#ff9800`)
  - Class/Type: Purple (`#9c27b0`)
  - ABV: Green (`#4caf50`)
  - Net Contents: Blue (`#2196f3`)
  - Warning: Red (`#f44336`)
- Interactive field selection and hover effects
- Field adjustment capability (drag/resize bounding boxes)

**User Experience**:
- Provides transparency into OCR extraction process
- Helps users understand what the system detected
- Allows manual correction of bounding boxes

**Future Potential**:
1. **Training Data Collection**: 
   - Users can adjust bounding boxes to correct OCR errors
   - Corrections could be collected as training data
   - Enables iterative improvement of OCR accuracy

2. **Neural Model Training**:
   - Collected corrections could train a more complex neural model
   - Custom OCR system optimized for TTB label format
   - Domain-specific improvements over general-purpose OCR

3. **Refinement Needs**:
   - Current implementation needs UI/UX improvements
   - Better handling of overlapping boxes
   - More intuitive adjustment controls
   - Validation of adjusted regions

---

## Implementation Details

### OCR Engine Factory

**Location**: `backend/app/services/label_engine/ocr_local.py`

**Factory Function**: `get_label_engine()`

**Selection Logic**:
```python
if USE_DUMMY_ENGINE:
    return DummyOCREngine()  # For testing
if OCR_ENGINE == "easyocr":
    return EasyOCREngine()
return PaddleOCREngine()  # Default
```

**Lazy Initialization**:
- OCR readers initialized on first use (singleton pattern)
- Reduces startup time and memory usage
- Allows runtime engine switching via environment variables

### Frontend Architecture

**Structure**:
- `frontend/index.html`: Main HTML with HTMX attributes
- `frontend/static/app.js`: Vanilla JavaScript for interactions
- `frontend/static/styles.css`: Styling
- `frontend/src/`: React code (not used in production, legacy/alternative)

**HTMX Integration**:
- Form submission: `hx-post="/api/verify"`
- Loading indicators: `hx-indicator="#processing-indicator"`
- Event handling: `hx-on::after-request="handleVerifyResponse(event)"`
- No automatic DOM swapping: `hx-swap="none"` (manual handling)

### Backend API

**Endpoints**:
- `POST /api/verify`: Main verification endpoint
- `POST /api/verify/adjust_field`: Field adjustment with re-OCR
- `GET /api/selftest/ocr`: Automated OCR testing
- `GET /health`: Health check

**Response Structure**:
- Structured JSON with field checks
- Bounding box coordinates for visualization
- Confidence metrics
- Overall verification status

### Docker Configuration

**Containerization**:
- Python 3.10 slim base image
- System dependencies for PaddleOCR/OpenCV
- Hot reloading support via volume mounts
- Environment variable configuration

**Deployment**:
- Docker Compose for local development and self-hosting
- Health checks configured
- Port 8000 exposed

---

## Future Considerations

### OCR Model Evolution

1. **Ovis2-8B Integration**:
   - Evaluate for dedicated hardware deployments
   - Higher accuracy potential
   - Requires more computational resources

2. **Automated Model Evaluation**:
   - Pipeline to test multiple OCR engines
   - Performance metrics collection
   - Automatic best-model selection

3. **Custom Model Training**:
   - Domain-specific OCR model for TTB labels
   - Training data collection via box adjustment feature
   - Iterative improvement based on user corrections

### Feature Enhancements

1. **Box Highlight Refinement**:
   - Improved UI/UX for field adjustment
   - Better handling of complex layouts
   - Validation and error handling

2. **Training Data Pipeline**:
   - Collect user corrections as training data
   - Annotate bounding boxes for supervised learning
   - Build dataset for custom model training

3. **Advanced Verification**:
   - Multi-label support
   - Batch processing
   - Historical comparison

### Deployment Options

1. **On-Site Hosting**:
   - Security-focused architecture supports on-premises deployment
   - HTMX reduces attack surface
   - Modular design allows hardware-specific optimizations

2. **Dedicated Hardware**:
   - Ovis2-8B model for high-performance scenarios
   - GPU acceleration support
   - Optimized for high-volume processing

3. **Hybrid Approach**:
   - Cloud for development/testing
   - On-site for production
   - Consistent architecture across environments

---

## References

- **OCR Logic Documentation**: See `ocr_logic.md` for detailed extraction algorithms
- **Extraction Summary**: See `EXTRACTION_LOGIC_SUMMARY.md` for field extraction overview
- **Codebase**: Implementation in `backend/app/services/label_engine/`
- **Frontend**: HTMX implementation in `frontend/index.html` and `frontend/static/app.js`

---
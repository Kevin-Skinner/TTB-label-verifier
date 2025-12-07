# TTB Label Verifier

A web application for verifying TTB (Alcohol and Tobacco Tax and Trade Bureau) labels against regulations.

## Project Structure

- `backend/` - FastAPI backend application
- `frontend/` - HTMX frontend application
- `docs/` - Project documentation

## Quick Start

### Docker (Recommended)

The easiest way to run the application is using Docker:

```bash
# Using docker-compose (recommended)
docker-compose up --build

# Or using the test script
# Linux/Mac:
./test-docker.sh

# Windows PowerShell:
.\test-docker.ps1

# Windows CMD:
test-docker.bat
```

The application will be available at `http://localhost:8000`

### Local Development

#### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

#### Frontend

The frontend is now served directly by the FastAPI backend. No separate frontend server is needed.

## Docker Testing

### Quick Start with Docker Compose

The simplest way to test the Docker build:

```bash
docker-compose up --build
```

This will:
- Build the Docker image
- Start the container on port 8000
- Make the application available at `http://localhost:8000`

To run in detached mode (background):
```bash
docker-compose up -d --build
```

To stop:
```bash
docker-compose down
```

### Using Helper Scripts

We provide platform-specific scripts for testing:

**Linux/Mac:**
```bash
chmod +x test-docker.sh
./test-docker.sh
```

**Windows PowerShell:**
```powershell
.\test-docker.ps1
```

**Windows CMD:**
```cmd
test-docker.bat
```

These scripts will:
- Build the Docker image
- Run the container
- Wait for the health check
- Display the access URL
- Handle cleanup on exit (Ctrl+C)

### Using Makefile

If you have `make` installed, you can use these commands:

```bash
make docker-build    # Build the image
make docker-run      # Run with docker-compose
make docker-test     # Build and test
make docker-clean    # Stop and remove containers
make docker-logs     # View container logs
make docker-stop     # Stop running container
```

### Manual Docker Commands

If you prefer to run Docker commands manually:

```bash
# Build the image
docker build -t ttb-label-verifier:local .

# Run the container
docker run -d -p 8000:8000 --name ttb-test ttb-label-verifier:local

# View logs
docker logs -f ttb-test

# Stop and remove
docker stop ttb-test && docker rm ttb-test
```

### Environment Variables

You can configure the application using environment variables:

- `OCR_ENGINE`: Set to `"paddleocr"` (default) or `"easyocr"`
- `USE_DUMMY_ENGINE`: Set to `"true"` to use a dummy engine for faster testing
- `SELFTEST_BASE_URL`: Set to `"http://localhost:8000"` to run automated tests against the running Docker container via HTTP. If not set, uses TestClient for in-process testing.

Create a `.env` file (see `.env.example`) or set them when running:

```bash
# Using docker-compose with custom environment
OCR_ENGINE=easyocr docker-compose up

# Using docker run
docker run -d -p 8000:8000 -e OCR_ENGINE=easyocr ttb-label-verifier:local

# To test against running Docker container
docker run -d -p 8000:8000 -e SELFTEST_BASE_URL=http://localhost:8000 ttb-label-verifier:local
```

### Running Automated Tests

The application includes automated OCR tests that can be run in two modes:

**1. In-process testing (default):**
- Uses FastAPI's TestClient for fast, in-process testing
- No environment variable needed
- Access via the "Run Automated OCR Tests" button in the UI or `/api/selftest/ocr` endpoint

**2. HTTP testing against Docker container:**
- Tests the actual running Docker container via HTTP requests
- Set `SELFTEST_BASE_URL=http://localhost:8000` in `docker-compose.yml` or as an environment variable
- Useful for testing the deployed application end-to-end
- Ensures the full stack (including network, file I/O, etc.) is tested

To enable HTTP testing mode, uncomment the `SELFTEST_BASE_URL` line in `docker-compose.yml`:

```yaml
environment:
  - SELFTEST_BASE_URL=http://localhost:8000
```

The test files (`backend/tests/form_submissions.csv` and `backend/tests/images/`) are automatically copied into the Docker container during build.

### Troubleshooting

**Port 8000 already in use:**
- Change the port mapping in `docker-compose.yml`: `"8001:8000"`
- Or use: `docker run -p 8001:8000 ...`

**Build takes a long time:**
- This is normal on first build. PaddleOCR downloads large model files (~500MB)
- Subsequent builds will be faster due to Docker layer caching

**Container exits immediately:**
- Check logs: `docker logs ttb-test` or `docker-compose logs`
- Verify all required files are present (frontend/static/, backend/, etc.)

**Static files not loading:**
- Ensure `frontend/static/app.js` and `frontend/static/styles.css` exist
- Check that `frontend/index.html` exists

**Health check fails:**
- Wait a bit longer - the application may need time to start
- Check container logs for errors
- Verify PaddleOCR dependencies installed correctly

## Verification Rules

### Mandatory Fields

The following fields are mandatory for label verification:
- **Brand**: Product brand name
- **Class/Type**: One of "Distilled Spirits", "Wine", "Malt Beverages", or "N/A"
- **ABV**: Alcohol by volume percentage (or "n/a" if not applicable)
- **Net Contents**: Volume with unit (e.g., "750 ml") or "n/a" if not applicable
- **Warning**: Government warning must be present on the label

### Warning Requirement

**Important**: Labels must have a government warning present. If the warning is not present (either unchecked in the form or not detected by OCR), the overall verification status will be **FAIL** with the note "Labels must have warning", even if all other fields match correctly.

### Status Determination

- **PASS**: All mandatory fields pass verification
- **FAIL**: Any mandatory field fails OR warning is missing
- **REVIEW**: Some fields require manual review (e.g., OCR confidence too low, field not detected)

## License

MIT


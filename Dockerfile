# Use Python 3.10 slim as base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies for PaddleOCR and OpenCV
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libgthread-2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgcc-s1 \
    && rm -rf /var/lib/apt/lists/*

# Set environment variable for OpenMP (required by PaddlePaddle)
ENV KMP_DUPLICATE_LIB_OK=TRUE

# Copy backend files
COPY backend/ /app/backend/

# Copy frontend static files
COPY frontend/static/ /app/frontend/static/
COPY frontend/index.html /app/frontend/index.html

# Copy test files for automated testing
COPY backend/tests/ /app/backend/tests/

# Install Python dependencies
WORKDIR /app/backend
RUN pip install --no-cache-dir -r requirements.txt

# Set working directory back to backend for uvicorn
WORKDIR /app/backend

# Expose port 8000
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


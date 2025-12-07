# TTB Label Verifier - Docker Test Script (PowerShell)
# Builds and runs the Docker container for local testing

$ErrorActionPreference = "Stop"

$IMAGE_NAME = "ttb-label-verifier"
$IMAGE_TAG = "local"
$CONTAINER_NAME = "ttb-test"
$PORT = 8000
$HEALTH_URL = "http://localhost:${PORT}/health"

# Cleanup function
function Cleanup {
    Write-Host "`nCleaning up..." -ForegroundColor Yellow
    docker stop $CONTAINER_NAME 2>$null
    docker rm $CONTAINER_NAME 2>$null
    Write-Host "Cleanup complete." -ForegroundColor Green
}

# Register cleanup on exit
Register-EngineEvent PowerShell.Exiting -Action { Cleanup } | Out-Null

Write-Host "=== TTB Label Verifier - Docker Test ===" -ForegroundColor Green
Write-Host ""

# Step 1: Build the image
Write-Host "Step 1: Building Docker image..." -ForegroundColor Yellow
docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" .

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed!" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Image built successfully" -ForegroundColor Green
Write-Host ""

# Step 2: Stop and remove existing container if it exists
Write-Host "Step 2: Cleaning up existing containers..." -ForegroundColor Yellow
docker stop $CONTAINER_NAME 2>$null
docker rm $CONTAINER_NAME 2>$null
Write-Host "✓ Cleanup complete" -ForegroundColor Green
Write-Host ""

# Step 3: Run the container
Write-Host "Step 3: Starting container..." -ForegroundColor Yellow
docker run -d `
    --name $CONTAINER_NAME `
    -p "${PORT}:8000" `
    "${IMAGE_NAME}:${IMAGE_TAG}"

if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to start container!" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Container started" -ForegroundColor Green
Write-Host ""

# Step 4: Wait for container to be ready
Write-Host "Step 4: Waiting for application to be ready..." -ForegroundColor Yellow
$MAX_ATTEMPTS = 30
$ATTEMPT = 0
$READY = $false

while ($ATTEMPT -lt $MAX_ATTEMPTS) {
    try {
        $response = Invoke-WebRequest -Uri $HEALTH_URL -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            Write-Host "✓ Application is ready!" -ForegroundColor Green
            Write-Host ""
            $READY = $true
            break
        }
    } catch {
        # Continue waiting
    }
    
    $ATTEMPT++
    Write-Host "." -NoNewline
    Start-Sleep -Seconds 2
}

if (-not $READY) {
    Write-Host ""
    Write-Host "Application did not become ready in time." -ForegroundColor Red
    Write-Host "Checking container logs..." -ForegroundColor Yellow
    docker logs $CONTAINER_NAME
    exit 1
}

# Step 5: Test health endpoint
Write-Host "Step 5: Testing health endpoint..." -ForegroundColor Yellow
try {
    $healthResponse = Invoke-WebRequest -Uri $HEALTH_URL -UseBasicParsing
    Write-Host "✓ Health check response: $($healthResponse.Content)" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "Warning: Health check failed" -ForegroundColor Yellow
    Write-Host ""
}

# Step 6: Display success message
Write-Host "========================================" -ForegroundColor Green
Write-Host "✓ Docker test completed successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Application is running at: http://localhost:${PORT}" -ForegroundColor Green
Write-Host "API docs available at: http://localhost:${PORT}/docs" -ForegroundColor Green
Write-Host ""
Write-Host "To stop the container, press Ctrl+C or run:" -ForegroundColor Yellow
Write-Host "  docker stop $CONTAINER_NAME; docker rm $CONTAINER_NAME"
Write-Host ""
Write-Host "To view logs:" -ForegroundColor Yellow
Write-Host "  docker logs -f $CONTAINER_NAME"
Write-Host ""

# Keep container running (wait for interrupt)
Write-Host "Container is running. Press Ctrl+C to stop..." -ForegroundColor Yellow
try {
    docker logs -f $CONTAINER_NAME
} finally {
    Cleanup
}


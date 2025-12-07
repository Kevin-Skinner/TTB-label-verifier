#!/bin/bash

# TTB Label Verifier - Docker Test Script
# Builds and runs the Docker container for local testing

set -e  # Exit on error

IMAGE_NAME="ttb-label-verifier"
IMAGE_TAG="local"
CONTAINER_NAME="ttb-test"
PORT=8000
HEALTH_URL="http://localhost:${PORT}/health"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}Cleaning up...${NC}"
    docker stop ${CONTAINER_NAME} 2>/dev/null || true
    docker rm ${CONTAINER_NAME} 2>/dev/null || true
    echo -e "${GREEN}Cleanup complete.${NC}"
}

# Set trap to cleanup on exit or interrupt
trap cleanup EXIT INT TERM

echo -e "${GREEN}=== TTB Label Verifier - Docker Test ===${NC}\n"

# Step 1: Build the image
echo -e "${YELLOW}Step 1: Building Docker image...${NC}"
docker build -t ${IMAGE_NAME}:${IMAGE_TAG} .

if [ $? -ne 0 ]; then
    echo -e "${RED}Build failed!${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Image built successfully${NC}\n"

# Step 2: Stop and remove existing container if it exists
echo -e "${YELLOW}Step 2: Cleaning up existing containers...${NC}"
docker stop ${CONTAINER_NAME} 2>/dev/null || true
docker rm ${CONTAINER_NAME} 2>/dev/null || true
echo -e "${GREEN}✓ Cleanup complete${NC}\n"

# Step 3: Run the container
echo -e "${YELLOW}Step 3: Starting container...${NC}"
docker run -d \
    --name ${CONTAINER_NAME} \
    -p ${PORT}:8000 \
    ${IMAGE_NAME}:${IMAGE_TAG}

if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to start container!${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Container started${NC}\n"

# Step 4: Wait for container to be ready
echo -e "${YELLOW}Step 4: Waiting for application to be ready...${NC}"
MAX_ATTEMPTS=30
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if curl -s -f ${HEALTH_URL} > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Application is ready!${NC}\n"
        break
    fi
    
    ATTEMPT=$((ATTEMPT + 1))
    echo -n "."
    sleep 2
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo -e "\n${RED}Application did not become ready in time.${NC}"
    echo -e "${YELLOW}Checking container logs...${NC}"
    docker logs ${CONTAINER_NAME}
    exit 1
fi

# Step 5: Test health endpoint
echo -e "${YELLOW}Step 5: Testing health endpoint...${NC}"
HEALTH_RESPONSE=$(curl -s ${HEALTH_URL})
echo -e "${GREEN}✓ Health check response: ${HEALTH_RESPONSE}${NC}\n"

# Step 6: Display success message
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ Docker test completed successfully!${NC}"
echo -e "${GREEN}========================================${NC}\n"
echo -e "Application is running at: ${GREEN}http://localhost:${PORT}${NC}"
echo -e "API docs available at: ${GREEN}http://localhost:${PORT}/docs${NC}\n"
echo -e "${YELLOW}To stop the container, press Ctrl+C or run:${NC}"
echo -e "  docker stop ${CONTAINER_NAME} && docker rm ${CONTAINER_NAME}\n"
echo -e "${YELLOW}To view logs:${NC}"
echo -e "  docker logs -f ${CONTAINER_NAME}\n"

# Keep container running (wait for interrupt)
echo -e "${YELLOW}Container is running. Press Ctrl+C to stop...${NC}"
docker logs -f ${CONTAINER_NAME}


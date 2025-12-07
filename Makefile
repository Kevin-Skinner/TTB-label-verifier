# TTB Label Verifier - Makefile for Docker Operations

.PHONY: help docker-build docker-run docker-test docker-clean docker-logs docker-stop

# Default target
help:
	@echo "TTB Label Verifier - Docker Commands"
	@echo ""
	@echo "Available targets:"
	@echo "  make docker-build    - Build the Docker image"
	@echo "  make docker-run      - Run the container using docker-compose"
	@echo "  make docker-test     - Build and test using test script"
	@echo "  make docker-clean    - Stop and remove containers/images"
	@echo "  make docker-logs     - View container logs"
	@echo "  make docker-stop     - Stop the running container"
	@echo ""

# Build the Docker image
docker-build:
	@echo "Building Docker image..."
	docker build -t ttb-label-verifier:local .

# Run using docker-compose
docker-run:
	@echo "Starting container with docker-compose..."
	docker-compose up --build

# Run in detached mode
docker-run-detached:
	@echo "Starting container in detached mode..."
	docker-compose up -d --build
	@echo "Container started. Use 'make docker-logs' to view logs."

# Test using the test script (Unix/Linux/Mac)
docker-test:
	@if [ -f test-docker.sh ]; then \
		chmod +x test-docker.sh && ./test-docker.sh; \
	else \
		echo "test-docker.sh not found. Use 'make docker-build' and 'make docker-run' instead."; \
	fi

# Clean up containers and images
docker-clean:
	@echo "Stopping and removing containers..."
	-docker-compose down
	-docker stop ttb-test 2>/dev/null || true
	-docker rm ttb-test 2>/dev/null || true
	@echo "Removing images..."
	-docker rmi ttb-label-verifier:local 2>/dev/null || true
	@echo "Cleanup complete."

# View logs
docker-logs:
	@if docker ps -a --format '{{.Names}}' | grep -q 'ttb-label-verifier\|ttb-test'; then \
		docker-compose logs -f 2>/dev/null || docker logs -f ttb-test 2>/dev/null || docker logs -f ttb-label-verifier 2>/dev/null; \
	else \
		echo "No running containers found."; \
	fi

# Stop the container
docker-stop:
	@echo "Stopping containers..."
	-docker-compose stop
	-docker stop ttb-test 2>/dev/null || true
	@echo "Containers stopped."


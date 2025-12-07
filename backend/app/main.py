"""
Main FastAPI application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from .api.routes_verify import router as verify_router
from .api.routes_selftest import router as selftest_router

app = FastAPI(title="TTB Label Verifier API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers (before static files to ensure API routes take precedence)
app.include_router(verify_router, prefix="/api", tags=["verification"])
app.include_router(selftest_router, prefix="/api/selftest", tags=["selftest"])

# Serve static files (CSS, JS)
# Path from backend/app/main.py: go up to backend, then up to project root, then into frontend
# In Docker: /app/backend/app/main.py -> /app/backend -> /app -> /app/frontend
static_dir = Path(__file__).parent.parent.parent / "frontend" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Serve index.html for root and other routes (SPA fallback)
frontend_dir = Path(__file__).parent.parent.parent / "frontend"
index_path = frontend_dir / "index.html"

@app.get("/")
async def root():
    """Serve the main HTML page."""
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "TTB Label Verifier API"}

@app.get("/health")
async def health():
    return {"status": "ok"}


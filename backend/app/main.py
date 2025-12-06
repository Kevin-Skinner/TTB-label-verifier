"""
Main FastAPI application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.routes_verify import router as verify_router

app = FastAPI(title="TTB Label Verifier API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(verify_router, prefix="/api", tags=["verification"])

@app.get("/")
async def root():
    return {"message": "TTB Label Verifier API"}

@app.get("/health")
async def health():
    return {"status": "ok"}


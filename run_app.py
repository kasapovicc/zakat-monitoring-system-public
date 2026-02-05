#!/usr/bin/env python3
"""
Development launcher for Zekat app

Starts FastAPI server without menubar for rapid iteration and testing.
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.api.views import router as views_router

# Create FastAPI app
app = FastAPI(
    title="Zekat Monitor",
    description="Zakat monitoring and calculation API",
    version="0.1.0"
)

# Add CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include HTML template routes (no prefix for root paths)
app.include_router(views_router)

# Include API routes
app.include_router(api_router)


def main():
    """Start the development server"""
    print("Starting Zekat Monitor development server...")
    print("FastAPI server running at: http://localhost:8000")
    print("API docs available at: http://localhost:8000/docs")
    print("Press Ctrl+C to stop")

    uvicorn.run(
        "run_app:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
        reload=True  # Auto-reload on code changes for development
    )


if __name__ == "__main__":
    main()

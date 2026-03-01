"""
Static files configuration for serving frontend
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

def setup_static_files(app: FastAPI):
    """Configure static file serving"""
    
    # Mount static directory
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
    
    # Serve index.html at root
    @app.get("/")
    async def serve_frontend():
        """Serve the main frontend page"""
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "SOLDIA API v2.0 - Frontend not found. Please add index.html to /static/"}

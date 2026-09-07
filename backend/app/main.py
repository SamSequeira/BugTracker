from pathlib import Path
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .services.language_detector import detect_language
from .services.preprocessor import preprocess_code

from app.api.v1.repositories import router as repositories_router
from app.api.v1.candidate_issues import (
    router as candidate_issues_router
)
from app.api.v1.auth import router as auth_router
from app.core.config import settings
app = FastAPI(
    title="AI Bug Tracking System",
    version="1.0.0"
)

# Configure CORS for the explicitly configured local frontend origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files directory if present
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(
    repositories_router, 
    prefix="/api/v1",
    tags=["Repositories"]
)
app.include_router(candidate_issues_router)
app.include_router(
    auth_router,
    prefix="/api/v1",
    tags=["Authentication"],
)

@app.get("/")
async def root():
    return {"message": "AI Bug Tracking System API is running"}


@app.get("/review", response_class=HTMLResponse)
async def serve_review_dashboard():
    """Serve standalone ground-truth dataset review dashboard."""
    review_html = Path(__file__).resolve().parent / "static" / "review.html"
    if review_html.exists():
        return FileResponse(str(review_html))
    return HTMLResponse("<h1>Review dashboard static file not found</h1>", status_code=404)


@app.post("/detect-language")
async def detect_file_language(file: UploadFile = File(...)):
    # Read uploaded file
    content = await file.read()

    # Convert bytes to text
    source_code = content.decode("utf-8")

    # Detect programming language
    language = detect_language(file.filename)

    # Preprocess source code
    processed_code = preprocess_code(source_code, language)

    return {
        "filename": file.filename,
        "language": language,
        "processed_code": processed_code
    }



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["app"],
        reload_excludes=["repositories"],
    )

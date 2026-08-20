from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from .services.language_detector import detect_language
from .services.preprocessor import preprocess_code

from app.api.v1.repositories import router as repositories_router
from app.api.v1.candidate_issues import (
    router as candidate_issues_router
)
app = FastAPI(
    title="AI Bug Tracking System",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    repositories_router, 
    prefix="/api/v1",
    tags=["Repositories"]
)
app.include_router(candidate_issues_router)

@app.get("/")
async def root():
    return {"message": "AI Bug Tracking System API is running"}

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


from fastapi import FastAPI, UploadFile, File

from .services.language_detector import detect_language
from .services.preprocessor import preprocess_code
from fastapi import FastAPI

from app.api.v1.repositories import router as repositories_router

app = FastAPI(
    title="AI Bug Tracking System",
    version="1.0.0"
)

app.include_router(
    repositories_router, 
    prefix="/api/v1",
    tags=["Repositories"]
)

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


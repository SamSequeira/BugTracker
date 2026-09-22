from pathlib import Path
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .services.language_detector import detect_language
from .services.preprocessor import preprocess_code

from app.api.v1.auth import router as auth_router
from app.api.v1.repositories import router as repositories_router
from app.api.v1.candidate_issues import router as candidate_issues_router
from app.core.config import settings


app = FastAPI(
    title="AI Bug Tracking System",
    version="1.0.0",
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

# Mount API v1 Routers
app.include_router(
    auth_router,
    prefix="/api/v1",
    tags=["Authentication"],
)

app.include_router(
    repositories_router,
    prefix="/api/v1",
    tags=["Repositories"],
)

app.include_router(
    candidate_issues_router,
    prefix="/api/v1",
    tags=["Candidate Issues"],
)

# Legacy root aliases without /api/v1 prefix for backwards compatibility
app.include_router(
    auth_router,
    tags=["Authentication (Legacy)"],
    include_in_schema=False,
)

app.include_router(
    repositories_router,
    tags=["Repositories (Legacy)"],
    include_in_schema=False,
)

# Legacy alias for candidate issues at root
app.include_router(
    candidate_issues_router,
    tags=["Candidate Issues (Legacy)"],
    include_in_schema=False,
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
        "processed_code": processed_code,
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
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .services.language_detector import detect_language
from .services.preprocessor import preprocess_code

from app.api.v1.repositories import router as repositories_router
from app.api.v1.candidate_issues import router as candidate_issues_router
from app.api.v1.auth import router as auth_router
from app.api.v1.resolve import router as resolve_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from data.dbconnection.session import engine, AsyncSessionLocal
        from data.dbconnection.base import Base
        import app.models  # noqa: F401
        from app.models.user import User
        from app.core.security import hash_password
        from uuid import uuid4
        from sqlalchemy import select

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with AsyncSessionLocal() as session:
            for demo_email, demo_name in [
                ("alex.mercer@bugtracker.dev", "Alex Mercer"),
                ("sarah.chen@cloudsec.io", "Sarah Chen"),
            ]:
                res = await session.execute(select(User).where(User.email == demo_email))
                if not res.scalar_one_or_none():
                    user = User(
                        id=str(uuid4()),
                        name=demo_name,
                        email=demo_email,
                        password_hash=hash_password("SecurePass2026!"),
                    )
                    session.add(user)
            await session.commit()
    except Exception as e:
        print(f"[Warning] Auto-table migration notice: {e}")
    yield


app = FastAPI(
    title="AI Bug Tracking System",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS for local frontend dev servers (Vite 5173, React 3000, 8000, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files directory if present
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Mount API v1 Routers
app.include_router(
    auth_router,
    prefix="/api/v1",
    tags=["Authentication"],
)

app.include_router(
    repositories_router,
    prefix="/api/v1",
    tags=["Repositories"],
)

app.include_router(
    candidate_issues_router,
    prefix="/api/v1",
    tags=["Candidate Issues"],
)

# Alias Candidate Issues at root /candidate-issues for backward compatibility
app.include_router(
    candidate_issues_router,
    tags=["Candidate Issues (Legacy)"],
    include_in_schema=False,
)

# Resolution pipeline + PR bot
app.include_router(
    resolve_router,
    prefix="/api/v1",
    tags=["Resolution & PR Analysis"],
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
        "processed_code": processed_code,
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

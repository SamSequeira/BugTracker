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


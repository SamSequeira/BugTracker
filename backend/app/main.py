from fastapi import FastAPI

app = FastAPI(
    title="AI Bug Tracking System",
    version="1.0.0"
)


@app.get("/")
async def root():
    return {"message": "AI Bug Tracking System API is running"}
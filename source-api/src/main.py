from api.api_v1.api import api_router
from config import settings
from fastapi import FastAPI

app = FastAPI(title="CSV Ingestion API")

app.include_router(api_router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)

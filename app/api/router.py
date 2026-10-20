from fastapi import  APIRouter

from app.api.routes import comparisons,documents

api_router = APIRouter()

api_router.include_router(
    comparisons.router,
    prefix="/comparisons",
    tags=["Comparisons"]
)
api_router.include_router(
    documents.router,
    prefix="/documents",
    tags=["Documents"]
)
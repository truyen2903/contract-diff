from fastapi import  APIRouter

from app.api.routes import comparisons

api_router = APIRouter()

api_router.include_router(
    comparisons.router,
    prefix="/comparisons",
    tags=["Comparisons"]
)
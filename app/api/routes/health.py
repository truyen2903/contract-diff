from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter()

# async: không chạy trong threadpool, vẫn trả lời khi các worker PDF bị chiếm.
@router.get("", response_model=HealthResponse)
async def health_endpoint():
    return {"status": "ok"}

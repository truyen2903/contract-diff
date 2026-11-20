from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

from app.api.router import api_router
from app.core.config import MAX_REQUEST_BODY_BYTES
from app.core.worker import WorkerBusyError, WorkerCrashedError, WorkerTimeoutError


app = FastAPI(title="ContractDiff")

app.add_middleware(RequestBodyLimitMiddleware, max_body_size=MAX_REQUEST_BODY_BYTES)

@app.exception_handler(HTTPException)
async def error_code_exception_handler(request: Request, exc: HTTPException):
    # Lỗi nghiệp vụ có error_code trả body phẳng; lỗi khác giữ dạng mặc định.
    if isinstance(exc.detail, dict) and "error_code" in exc.detail:
        return JSONResponse(exc.detail, status_code=exc.status_code, headers=exc.headers)
    return await http_exception_handler(request, exc)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Giữ dạng 422 mặc định nhưng bỏ "input": không trả lại nguyên văn bản lớn
    # và tránh lỗi mã hóa UTF-8 khi input chứa surrogate lẻ (500 thay vì 422).
    errors = [
        {key: value for key, value in error.items() if key != "input"}
        for error in exc.errors()
    ]
    return JSONResponse({"detail": jsonable_encoder(errors)}, status_code=422)

# Lỗi của worker xử lý, cùng dạng body phẳng {"error_code", "detail"}.
@app.exception_handler(WorkerBusyError)
async def worker_busy_handler(request: Request, exc: WorkerBusyError):
    return JSONResponse(
        {"error_code": "SERVER_BUSY", "detail": "Máy chủ đang bận, vui lòng thử lại sau"},
        status_code=503,
        headers={"Retry-After": "5"},
    )

@app.exception_handler(WorkerTimeoutError)
async def worker_timeout_handler(request: Request, exc: WorkerTimeoutError):
    # Không kèm Retry-After: gửi lại cùng input sẽ lại quá hạn.
    return JSONResponse(
        {"error_code": "PROCESSING_TIMEOUT", "detail": "Xử lý vượt quá thời gian cho phép"},
        status_code=504,
    )

@app.exception_handler(WorkerCrashedError)
async def worker_crashed_handler(request: Request, exc: WorkerCrashedError):
    return JSONResponse(
        {"error_code": "PROCESSING_FAILED", "detail": "Xử lý tài liệu thất bại"},
        status_code=500,
    )

app.include_router(api_router, prefix="/api/v1")
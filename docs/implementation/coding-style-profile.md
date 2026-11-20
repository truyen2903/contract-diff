# Coding Style Profile — ContractDiff

Tài liệu ghi lại các quy ước **đã quan sát thực tế** trong code hiện có (code tại `a5e9c60`/`3304f00` + thay đổi chưa commit trên `main`, ngày 2026-11-19; đã hiệu chỉnh theo kiểm chứng của Claude Round 1). Mọi code mới và mọi reviewer dùng tài liệu này làm chuẩn đánh giá phong cách.

## 1. Tổ chức module (layering)

| Tầng | Thư mục | Quan sát | Bằng chứng |
|---|---|---|---|
| Route | `app/api/routes/` | Route rất mỏng: nhận input, gọi **một** hàm service, trả về dict. Không có business logic. | `comparisons.py:9-21`, `documents.py:7-12` |
| Router | `app/api/router.py` | Mỗi module route có `router = APIRouter()`; `api_router.include_router(module.router, prefix=..., tags=[...])`. Prefix `/api/v1` gắn ở `main.py`. | `router.py:7-16`, `main.py:8` |
| Service | `app/services/` | Hàm module-level (không class), điều phối extractor/engine, trả về **dict thuần** (`{"key": value}`) — Pydantic chỉ dùng ở tầng `response_model`. | `comparison_service.py:5-36`, `document_service.py:3-10` |
| Engine | `app/engines/` | Thuật toán thuần, không phụ thuộc FastAPI/Pydantic, input/output là `str`/`list[dict]`/`dict`. | `text_diff.py`, `text_mapping.py` |
| Extractor | `app/extractors/` | Bọc thư viện ngoài (`pdfplumber`), trả `list[dict]`. | `pdf_extractor.py:2-17` |
| Schema | `app/schemas/` | Pydantic `BaseModel`, một file theo miền (`comparison.py`, `document.py`), schema có thể import chéo. | `comparison.py:2` |

## 2. Naming

- `snake_case` cho hàm, biến, module; `PascalCase` cho schema (`TextComparisonRequest`, `PDFComparisonResponse` — giữ chữ viết tắt in hoa `PDF`).
- Hàm route kết thúc bằng `_endpoint` (`compare_text_endpoint`, `extract_document_endpoint`).
- Hàm service đặt tên động từ + danh từ: `compare_text`, `compare_document`, `extract_document`.
- Schema response kết thúc bằng `Response`, request bằng `Request`.
- Biến ngắn gọn, mô tả: `old_document`, `new_data`, `page_ranges`, `changes`.

## 3. Hàm và kiểu

- Hàm module-level, nhỏ, một trách nhiệm. Không class, không base class, không decorator tự viết.
- Type hints **không đồng nhất** ở mọi tầng: `diff_words` có đủ hint, `tokenize_with_spans(text)` không có; `compare_text` có hint tham số nhưng không hint trả về; `extract_document(filename, file_stream)` không có. Code mới: thêm hint ở mức tương tự hàm lân cận, không ép bổ sung hint cho code cũ.
- Kiểu dữ liệu trao đổi giữa tầng: `dict` với key chuỗi; trường `None` khi vắng mặt (`old_span = None`).
- Logic tường minh: phần lớn là vòng `for` + `append` (`tokenize_with_spans`, `span_to_page_locations`); có dùng comprehension/generator đơn giản (`text_diff.py:17-18`, `comparison_service.py:22-23`), không dùng comprehension phức tạp.

## 4. Import

- Import thư viện ngoài trước, rồi import `app.*` tuyệt đối. Dòng trống giữa hai nhóm và thứ tự trong nhóm **không nhất quán** (có ở `comparisons.py`, không có ở `documents.py`, `pdf_extractor.py`). Code mới: ngoài → dòng trống → `app.*`.
- Không dùng import tương đối.
- Nhập nhiều tên trong ngoặc trên một dòng: `from app.schemas.comparison import (A, B, C)`.

## 5. Schema Pydantic

- `BaseModel` + annotation; ràng buộc bằng `Field(...)` (`Field(min_length=1)`).
- Trường tùy chọn: `X | None` (cú pháp PEP 604), không dùng `Optional`.
- Giá trị mặc định list viết `= []` (Pydantic tự copy, an toàn) — `comparison.py:24-25`.
- Chưa có `field_validator`, `Enum`, `model_config` trong code hiện tại.

## 6. Xử lý lỗi

- **Hiện chưa có** xử lý lỗi tường minh nào (không `try/except`, không `HTTPException`). Lỗi validation hoàn toàn dựa vào FastAPI/Pydantic (422 mặc định).
- Đây là khoảng trống đúng đắn cần lấp (kế hoạch v2 §3.2), không phải phong cách cần giữ. Khi thêm: ưu tiên cơ chế có sẵn của FastAPI (`HTTPException`), đặt ở chỗ đơn giản nhất, không tạo hệ thống exception class riêng nếu không cần.

## 7. Formatting

- Thụt lề 4 dấu cách. Không có formatter/linter được cấu hình (không có `ruff`/`black` config).
- Khoảng trắng chưa đồng nhất (`from fastapi import  APIRouter`, `pages= extract_pdf(...)`, `"filename":filename`). **Không** reformat code cũ ngoài phạm vi thay đổi.
- `app/` không có comment/docstring nào; `tests/` có comment/docstring tiếng Việt ngắn. Code mới trong `app/` giữ tối thiểu comment.
- Line ending lẫn lộn (CRLF ở `comparison_service.py`, LF ở `comparisons.py`, `text_mapping.py`): giữ nguyên line ending của file đang sửa.
- `__pycache__/*.pyc` đang bị git theo dõi (`.gitignore` chỉ có `.venv`) — không xử lý trong phạm vi endpoint, chỉ ghi nhận.

## 8. Kiểm thử

- `pytest` + `fastapi.testclient.TestClient` dùng như context manager trong fixture `client`.
- Helper module-level nhỏ trong file test (`post_pdf_pair`, `successful_json`, `changes_signature`).
- Hằng số viết HOA ở đầu file (`API_URL`, `FIXTURES`, `EXPECTED_CHANGES`).
- `@pytest.mark.parametrize` cho các ca đối xứng.
- Fixture PDF thật trong `tests/fixtures/`.
- Test kiểm tra hành vi quan sát được qua API (status code, JSON), kèm `response.text` trong message assert.

## 9. Quy tắc áp dụng cho code mới

1. Route mỏng; logic vào service; thuật toán vào engine/extractor.
2. Service trả dict; route gắn `response_model`.
3. Không thêm class/abstraction/thư viện nếu standard library hoặc FastAPI đã đủ.
4. Chỉ sửa dòng cần sửa; không reformat code cũ.
5. Tên mới theo mẫu: hàm route `*_endpoint`; module service `*_service.py` (hàm service không hậu tố); schema `*Request`/`*Response`.
7. Không có `__init__.py` (namespace package) — không thêm.
6. Ngoại lệ có chủ đích được ghi rõ trong báo cáo cuối.

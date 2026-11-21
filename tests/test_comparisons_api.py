"""Kiểm thử API bằng hai PDF giả lập CT-DIFF-001 đã dùng trong dự án."""

from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import MAX_REQUEST_BODY_BYTES, MAX_TEXT_CHARS
from app.main import app
from app.services import document_service


API_URL = "/api/v1/comparisons/pdf"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
OLD_PDF = FIXTURES / "contract_old.pdf"
NEW_PDF = FIXTURES / "contract_new.pdf"

EXPECTED_CHANGES = [
    ("replace", "12.000.000", "15.000.000"),
    ("replace", "30", "15"),
    ("insert", "", "không"),
    ("delete", "Bên B gửi báo cáo tiến độ vào thứ Hai hằng tuần.", ""),
    ("insert", "", "Hai bên xác nhận nghiệm thu bằng văn bản."),
]


@pytest.fixture
def client():
    # Context manager chạy cả phần khởi động và kết thúc của app.
    with TestClient(app) as test_client:
        yield test_client


def post_pdf_pair(client, old_path, new_path):
    # Mở mới hai stream trong mỗi lần gọi, kể cả khi cùng một đường dẫn.
    with old_path.open("rb") as old_file, new_path.open("rb") as new_file:
        return client.post(
            API_URL,
            files={
                "old_file": (old_path.name, old_file, "application/pdf"),
                "new_file": (new_path.name, new_file, "application/pdf"),
            },
        )


def successful_json(response):
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    return response.json()


def changes_signature(data):
    # Kiểm tra cả nội dung và số lần xuất hiện, không buộc thứ tự trả về.
    return Counter(
        (change["type"], change["old_text"], change["new_text"])
        for change in data["changes"]
    )


def assert_source_locations(data):
    """Mỗi vị trí phải trỏ đúng văn bản nguồn và đúng span toàn tài liệu."""
    for side in ("old", "new"):
        document = data[f"{side}_document"]
        assert document["page_count"] == len(document["pages"]) == 2

        pages = {}
        page_start = 0
        for page in document["pages"]:
            assert page["warnings"] == []
            pages[page["page_number"]] = (page["text"], page_start)
            page_start += len(page["text"]) + 2

        for change in data["changes"]:
            span = change[f"{side}_span"]
            locations = change[f"{side}_locations"]
            fragment = change[f"{side}_text"]

            if span is None:
                assert fragment == ""
                assert locations == []
                continue

            # Năm thay đổi của bộ PDF này đều nằm gọn trong từng trang.
            assert len(locations) == 1
            location = locations[0]
            page_text, page_start = pages[location["page_number"]]
            start, end = location["start"], location["end"]

            assert 0 <= start < end <= len(page_text)
            assert page_text[start:end] == fragment
            assert page_start + start == span["start"]
            assert page_start + end == span["end"]


def test_old_to_new_returns_five_expected_changes(client):
    data = successful_json(post_pdf_pair(client, OLD_PDF, NEW_PDF))

    assert changes_signature(data) == Counter(EXPECTED_CHANGES)
    assert data["needs_review"] is False
    assert_source_locations(data)


def test_identical_pdfs_return_no_changes(client):
    data = successful_json(post_pdf_pair(client, OLD_PDF, OLD_PDF))

    assert data["changes"] == []
    assert data["needs_review"] is False
    assert data["old_document"]["pages"] == data["new_document"]["pages"]
    assert_source_locations(data)


def test_new_to_old_reverses_changes(client):
    data = successful_json(post_pdf_pair(client, NEW_PDF, OLD_PDF))

    inverse_type = {"replace": "replace", "insert": "delete", "delete": "insert"}
    expected = [
        (inverse_type[kind], new_text, old_text)
        for kind, old_text, new_text in EXPECTED_CHANGES
    ]

    assert changes_signature(data) == Counter(expected)
    assert data["needs_review"] is False
    assert_source_locations(data)


@pytest.mark.parametrize("missing_field", ["old_file", "new_file"])
def test_missing_required_file_returns_422(client, missing_field):
    present_field = "new_file" if missing_field == "old_file" else "old_file"

    with OLD_PDF.open("rb") as pdf:
        response = client.post(
            API_URL,
            files={present_field: (OLD_PDF.name, pdf, "application/pdf")},
        )

    assert response.status_code == 422, response.text
    assert any(
        error["loc"][-1] == missing_field
        for error in response.json()["detail"]
    )


# ── Phase A: health, /text và kiểm tra đầu vào PDF ───────

TEXT_URL = "/api/v1/comparisons/text"
STRUCTURED_TEXT_URL = "/api/v1/comparisons/structured/text"
STRUCTURED_PDF_URL = "/api/v1/comparisons/structured/pdf"
EXTRACT_URL = "/api/v1/documents/extract"


def assert_api_error(response, status_code, error_code):
    assert response.status_code == status_code, response.text
    assert response.json()["error_code"] == error_code
    assert isinstance(response.json()["detail"], str)


def test_health_returns_ok(client):
    response = client.get("/api/v1/health")

    assert successful_json(response) == {"status": "ok"}


def test_text_comparison_vietnamese(client):
    response = client.post(TEXT_URL, json={
        "old_text": "Thời hạn thanh toán là 30 ngày.",
        "new_text": "Thời hạn thanh toán là 15 ngày.",
    })
    data = successful_json(response)

    assert set(data) == {"is_identical", "is_token_identical", "old_length", "new_length", "changes"}
    assert data["is_identical"] is False
    assert data["is_token_identical"] is False
    assert [(c["type"], c["old_text"], c["new_text"]) for c in data["changes"]] == [
        ("replace", "30", "15"),
    ]


def test_structured_text_returns_real_b1_b2_b3_result(client):
    response = client.post(STRUCTURED_TEXT_URL, json={
        "old_text": "Điều 1: Thanh toán\n1. Bên mua phải thanh toán 100 USD trong 30 ngày.",
        "new_text": "Điều 1: Thanh toán\n1. Bên mua phải thanh toán 120 USD trong 30 ngày làm việc.",
    })
    data = successful_json(response)
    assert data["b3_schema_version"] == "b3-v1"
    assert data["old_document"]["nodes"]
    assert data["new_document"]["nodes"]
    assert any(row["entity_deltas"] for row in data["alignments"])
    assert any(delta["signal_type"] == "MONEY_CHANGE"
               for row in data["alignments"] for delta in row["entity_deltas"])


@pytest.mark.parametrize("payload", [{"old_text": "a"}, {"new_text": "a"}, {"old_text": " ", "new_text": "b"}])
def test_structured_text_validation_is_safe(client, payload):
    response = client.post(STRUCTURED_TEXT_URL, json=payload)
    assert response.status_code == 422
    assert "input" not in response.text


def test_structured_pdf_returns_real_result(client):
    response = client.post(STRUCTURED_PDF_URL, files={
        "old_file": (OLD_PDF.name, OLD_PDF.read_bytes(), "application/pdf"),
        "new_file": (NEW_PDF.name, NEW_PDF.read_bytes(), "application/pdf"),
    })
    data = successful_json(response)
    assert data["old_document"]["source_type"] == "PDF_DIGITAL"
    assert data["new_document"]["source_type"] == "PDF_DIGITAL"
    assert data["alignments"]


@pytest.mark.parametrize("missing_field", ["old_file", "new_file"])
def test_structured_pdf_missing_file_returns_422(client, missing_field):
    present_field = "new_file" if missing_field == "old_file" else "old_file"
    response = client.post(STRUCTURED_PDF_URL, files={present_field: (OLD_PDF.name, OLD_PDF.read_bytes(), "application/pdf")})
    assert response.status_code == 422
    assert any(error["loc"][-1] == missing_field for error in response.json()["detail"])


def test_text_comparison_whitespace_only_difference(client):
    data = successful_json(client.post(TEXT_URL, json={"old_text": "a b", "new_text": "a\n b"}))

    assert data["is_identical"] is False
    assert data["is_token_identical"] is True
    assert data["changes"] == []


@pytest.mark.parametrize("blank", ["", "   ", "\n\t", " 　", "\x1c"])
def test_text_comparison_rejects_blank_text(client, blank):
    response = client.post(TEXT_URL, json={"old_text": "a", "new_text": blank})

    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"][-1] == "new_text"


@pytest.mark.parametrize("payload", [
    {"old_text": "a"},
    {"new_text": "a"},
    {"old_text": None, "new_text": "a"},
    {"old_text": 1, "new_text": "a"},
])
def test_text_comparison_rejects_missing_or_wrong_fields(client, payload):
    assert client.post(TEXT_URL, json=payload).status_code == 422


def test_text_comparison_length_limit(client):
    ok = client.post(TEXT_URL, json={"old_text": "a" * MAX_TEXT_CHARS, "new_text": "a"})
    too_long = client.post(TEXT_URL, json={"old_text": "a" * (MAX_TEXT_CHARS + 1), "new_text": "a"})

    assert ok.status_code == 200, ok.text
    assert too_long.status_code == 422
    assert too_long.json()["detail"][0]["type"] == "string_too_long"


def test_extract_returns_pages(client):
    with OLD_PDF.open("rb") as pdf:
        response = client.post(EXTRACT_URL, files={"file": (OLD_PDF.name, pdf, "application/pdf")})
    data = successful_json(response)

    assert data["filename"] == OLD_PDF.name
    assert data["page_count"] == len(data["pages"]) == 2


def test_extract_accepts_pdf_content_with_wrong_extension(client, make_pdf):
    response = client.post(
        EXTRACT_URL,
        files={"file": ("contract.txt", make_pdf(["Hello"]), "text/plain")},
    )

    assert successful_json(response)["pages"][0]["text"] == "Hello"


def test_extract_accepts_owner_only_encrypted_pdf(client, make_pdf):
    response = client.post(
        EXTRACT_URL,
        files={"file": ("locked.pdf", make_pdf(["Hello"], encryption="owner_only"), "application/pdf")},
    )

    assert successful_json(response)["pages"][0]["text"] == "Hello"


INVALID_PDF_CASES = {
    "empty": lambda make_pdf: b"",
    "text_named_pdf": lambda make_pdf: b"hello world",
    "garbage_after_magic": lambda make_pdf: b"%PDF-1.7\nnot-a-document",
    "user_password": lambda make_pdf: make_pdf(["x"], encryption="user_password"),
    "zero_pages": lambda make_pdf: make_pdf([]),
    "malformed_page": lambda make_pdf: make_pdf(["x"], page_extra=b"/Rotate /Invalid"),
}


@pytest.mark.parametrize("case", INVALID_PDF_CASES)
def test_extract_rejects_invalid_pdf(client, make_pdf, case):
    data = INVALID_PDF_CASES[case](make_pdf)

    response = client.post(EXTRACT_URL, files={"file": ("bad.pdf", data, "application/pdf")})

    assert_api_error(response, 400, "INVALID_OR_ENCRYPTED_PDF")


@pytest.mark.parametrize("bad_field", ["old_file", "new_file"])
def test_pdf_comparison_reports_which_file_is_invalid(client, bad_field):
    good = OLD_PDF.read_bytes()
    files = {
        "old_file": ("old.pdf", good, "application/pdf"),
        "new_file": ("new.pdf", good, "application/pdf"),
    }
    files[bad_field] = ("bad.pdf", b"hello", "application/pdf")

    response = client.post(API_URL, files=files)

    assert_api_error(response, 400, "INVALID_OR_ENCRYPTED_PDF")
    assert "bad.pdf" in response.json()["detail"]


def test_uploaded_file_size_limit(client, make_pdf, monkeypatch):
    data = make_pdf(["Hello"])
    monkeypatch.setattr(document_service, "MAX_UPLOAD_FILE_BYTES", len(data))

    ok = client.post(EXTRACT_URL, files={"file": ("ok.pdf", data, "application/pdf")})
    too_big = client.post(EXTRACT_URL, files={"file": ("big.pdf", data + b"\n", "application/pdf")})

    assert ok.status_code == 200, ok.text
    assert_api_error(too_big, 413, "PAYLOAD_TOO_LARGE")


def test_page_limit(client, make_pdf, monkeypatch):
    monkeypatch.setattr(document_service, "MAX_PDF_PAGES", 2)

    ok = client.post(EXTRACT_URL, files={"file": ("ok.pdf", make_pdf(["a", "b"]), "application/pdf")})
    too_many = client.post(EXTRACT_URL, files={"file": ("big.pdf", make_pdf(["a", "b", "c"]), "application/pdf")})

    assert ok.status_code == 200, ok.text
    assert_api_error(too_many, 422, "PDF_TOO_MANY_PAGES")


def test_request_body_limit_rejects_before_parsing(client):
    response = client.post(
        EXTRACT_URL,
        content=b"x" * (MAX_REQUEST_BODY_BYTES + 1),
        headers={"content-type": "multipart/form-data; boundary=x"},
    )

    assert response.status_code == 413


def test_blank_pdf_pages_need_review(client, make_pdf):
    blank = make_pdf([""])
    response = client.post(API_URL, files={
        "old_file": ("old.pdf", blank, "application/pdf"),
        "new_file": ("new.pdf", blank, "application/pdf"),
    })
    data = successful_json(response)

    assert data["changes"] == []
    assert data["needs_review"] is True
    assert data["old_document"]["pages"][0]["warnings"] == ["EMPTY_TEXT"]


def test_not_found_keeps_default_error_format(client):
    response = client.get("/api/v1/unknown")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_request_body_limit_rejects_chunked_body(client):
    def chunks():
        for _ in range(32):
            yield b"x" * (1024 * 1024)

    response = client.post(
        EXTRACT_URL,
        content=chunks(),
        headers={"content-type": "multipart/form-data; boundary=x"},
    )

    assert response.status_code == 413


def test_validation_error_does_not_echo_input(client):
    response = client.post(TEXT_URL, json={"old_text": "a" * (MAX_TEXT_CHARS + 1), "new_text": "a"})

    assert response.status_code == 422
    assert "input" not in response.json()["detail"][0]
    assert len(response.content) < 1000


def test_lone_surrogate_returns_422_not_500(client):
    response = client.post(
        TEXT_URL,
        content=rb'{"old_text": "a", "new_text": "\ud800"}',
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"][-1] == "new_text"

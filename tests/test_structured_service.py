from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core import jobs
from app.engines.alignment_budget import AlignmentBudgetError, AlignmentResultTooLargeError
from app.main import app
from app.services import structured_comparison_service as service


def test_normal_paths_use_one_worker_each(monkeypatch):
    calls = []
    original = service.run_in_worker
    def counted(job, *args, **kwargs):
        calls.append(job)
        return original(job, *args, **kwargs)
    monkeypatch.setattr(service, "run_in_worker", counted)
    assert service.compare_structured_text("identical", "identical")["alignments"][0]["category"] == "UNCHANGED"
    path = Path(__file__).parent / "fixtures/contract_old.pdf"
    with path.open("rb") as a, path.open("rb") as b:
        data = service.compare_structured_document(path.name, a, path.name, b)
    assert all(r["category"] == "UNCHANGED" for r in data["alignments"])
    assert calls == [jobs.compare_structured_texts, jobs.compare_structured_pdf_files]
    assert "/api/v1/comparisons/structured/text" in app.openapi()["paths"]
    assert "/api/v1/comparisons/structured/pdf" in app.openapi()["paths"]


@pytest.mark.parametrize("error,code", [(AlignmentBudgetError("orphan"), "ALIGNMENT_BUDGET_EXCEEDED"),
                                        (AlignmentResultTooLargeError("size"), "RESULT_TOO_LARGE")])
def test_domain_422(monkeypatch, error, code):
    def reject(*args, expected_errors):
        assert isinstance(error, expected_errors)
        raise error
    monkeypatch.setattr(service, "run_in_worker", reject)
    with pytest.raises(HTTPException) as exc:
        service.compare_structured_text("one", "two")
    assert (exc.value.status_code, exc.value.detail["error_code"]) == (422, code)


def test_input_validation_before_worker_and_parent_validation(monkeypatch):
    def bomb(*args, **kw):
        pytest.fail("expensive work for invalid input")
    monkeypatch.setattr(service, "run_in_worker", bomb)
    with pytest.raises(ValidationError):
        service.compare_structured_text(" ", "ok")
    with pytest.raises(HTTPException) as exc:
        service.compare_structured_document("a.pdf", BytesIO(b"%PDF-"), "bad.pdf", BytesIO(b"text"))
    assert exc.value.status_code == 400 and "bad.pdf" in exc.value.detail["detail"]
    monkeypatch.setattr(service, "run_in_worker", lambda *args, **kw: {})
    with pytest.raises(HTTPException) as exc:
        service.compare_structured_text("valid", "valid")
    assert exc.value.status_code == 500
    assert exc.value.detail == {"error_code": "PROCESSING_FAILED", "detail": "Kết quả structured không hợp lệ"}


def test_real_alignment_budget_maps_to_422():
    many = "\n".join(f"Điều {i}: A" for i in range(1, 226))
    with pytest.raises(HTTPException) as exc:
        service.compare_structured_text(many, many)
    assert exc.value.status_code == 422
    assert exc.value.detail["error_code"] == "ALIGNMENT_BUDGET_EXCEEDED"

import pickle
from pathlib import Path

import pytest

from app.core import config, jobs
from app.core.worker import run_in_worker
from app.engines import compact_alignment as compact
from app.engines.alignment_budget import (AlignmentBudget, AlignmentBudgetError, AlignmentResultTooLargeError,
                                          StructureTooLargeError)
from app.parsers.contract_parser import parse_contract_text
from app.schemas.alignment import StructuredComparisonResponse


def test_text_in_two_isolated_workers():
    args = ("Điều 1: Giao hàng\n1. Trong ba ngày.", "Điều 2: Giao hàng\n2. Trong sáu ngày.")
    first = run_in_worker(jobs.compare_structured_texts, *args)
    second = run_in_worker(jobs.compare_structured_texts, *args)
    assert pickle.dumps(first) == pickle.dumps(second)
    assert StructuredComparisonResponse.model_validate(first).alignments
    assert config.COMPARISON_TIMEOUT_SECONDS == 30 and config.MAX_WORKER_RESULT_BYTES == 32 * 1024**2


def test_b3_semantic_fields_are_worker_deterministic_and_strictly_validated():
    old = "Điều 1: Thanh toán\n1. Bên mua có nghĩa vụ thanh toán đầy đủ giá trị hợp đồng cho bên bán trong thời hạn 30 ngày kể từ ngày nhận hóa đơn, bằng 100 USD."
    new = "Điều 1: Thanh toán\n1. Bên mua có nghĩa vụ thanh toán đầy đủ giá trị hợp đồng cho bên bán trong thời hạn 30 ngày kể từ ngày nhận hóa đơn, bằng 100 VND."
    first = run_in_worker(jobs.compare_structured_texts, old, new)
    second = run_in_worker(jobs.compare_structured_texts, old, new)
    assert pickle.dumps(first) == pickle.dumps(second)
    checked = StructuredComparisonResponse.model_validate(first)
    row = next(row for row in checked.alignments if row.category == "MODIFIED")
    assert row.review_priority == "CRITICAL"
    assert row.entity_deltas[0].signal_type == "MONEY_CHANGE"
    assert checked.b3_schema_version == "b3-v1"


def test_relative_reference_result_validates_in_worker():
    old = "Điều 1: Thanh toán\n1. Theo khoản nêu trên, Bên B phải giao hàng đầy đủ trong thời hạn ba mươi ngày kể từ khi nhận yêu cầu."
    new = "Điều 1: Thanh toán\n1. Theo khoản nêu trên, Bên B phải giao hàng đầy đủ trong thời hạn bốn mươi ngày kể từ khi nhận yêu cầu."
    result = run_in_worker(jobs.compare_structured_texts, old, new)
    checked = StructuredComparisonResponse.model_validate(result)
    assert any(entity.evidence_scope == "UNRESOLVED"
               for row in checked.alignments for entity in row.old_entities + row.new_entities)


def test_renumbered_article_flags_unchanged_clause_reference():
    old = "Điều 1: X\n1. Theo Điều 1, Bên B giao hàng."
    new = "Điều 2: X\n1. Theo Điều 1, Bên B giao hàng."
    result = run_in_worker(jobs.compare_structured_texts, old, new)
    checked = StructuredComparisonResponse.model_validate(result)
    clause = next(row for row in checked.alignments if row.node_type == "CLAUSE")
    assert "INTERNAL_CROSS_REFERENCE_RISK" in clause.warnings
    assert clause.needs_review is True


def test_renumbered_article_flags_qualified_reference():
    old = "Điều 1: X\n1. Theo Khoản 1 Điều 1, Bên B giao hàng."
    new = "Điều 2: X\n1. Theo Khoản 1 Điều 1, Bên B giao hàng."
    result = run_in_worker(jobs.compare_structured_texts, old, new)
    clause = next(row for row in StructuredComparisonResponse.model_validate(result).alignments
                  if row.node_type == "CLAUSE")
    assert "INTERNAL_CROSS_REFERENCE_RISK" in clause.warnings


def test_renumbered_clause_flags_qualified_reference():
    old = "Điều 1: X\n1. Nội dung chính.\n2. Theo Khoản 1 Điều 1, Bên B giao hàng."
    new = "Điều 1: X\n2. Nội dung chính.\n3. Theo Khoản 1 Điều 1, Bên B giao hàng."
    result = run_in_worker(jobs.compare_structured_texts, old, new)
    rows = StructuredComparisonResponse.model_validate(result).alignments
    reference_row = next(row for row in rows if row.node_type == "CLAUSE" and row.category == "RENUMBERED"
                         and any("INTERNAL_CROSS_REFERENCE_RISK" == warning for warning in row.warnings))
    assert reference_row.needs_review is True


def test_pdf_worker_fixture():
    paths = [Path("tests/fixtures/contract_" + side + ".pdf") for side in ("old", "new")]
    with paths[0].open("rb") as old, paths[1].open("rb") as new:
        result = run_in_worker(jobs.compare_structured_pdf_files, files=[old, new])
    checked = StructuredComparisonResponse.model_validate(result)
    assert checked.old_document.source_type == "PDF_DIGITAL"
    assert len(checked.alignments) and checked.old_document.page_count >= 1


def test_node_limits_with_side_in_worker():
    large = "\n".join(f"Điều {i}: Heading" for i in range(1, 3002))
    with pytest.raises(StructureTooLargeError) as exc:
        run_in_worker(jobs.compare_structured_texts, "", large, expected_errors=(StructureTooLargeError,))
    assert exc.value.side == "new"


def test_local_diff_limit_precedes_matcher(monkeypatch):
    monkeypatch.setattr(compact, "diff_words", lambda *a: pytest.fail("unexpected diff"))
    old = parse_contract_text("Điều 1: Các bên giao hàng trong ba ngày.")
    new = parse_contract_text("Điều 1: Các bên giao hàng trong bốn ngày.")
    with pytest.raises(AlignmentBudgetError, match="diff_total"):
        compact.build_result(old, new, budget=AlignmentBudget(max_diff_total=1))
    monkeypatch.setattr(config, "MAX_DIFF_PAIR_WORK", 1)
    with pytest.raises(AlignmentBudgetError, match="local diff"):
        compact.build_result(old, new)


def test_lis_budget_and_opcode_limit(monkeypatch):
    tree = parse_contract_text("Điều 1: A\nĐiều 2: B")
    with pytest.raises(AlignmentBudgetError, match="weighted LIS"):
        compact.build_result(tree, tree, budget=AlignmentBudget(max_lis=3))
    monkeypatch.setattr(config, "MAX_CHANGE_OPCODES", 0)
    with pytest.raises(AlignmentResultTooLargeError):
        jobs.compare_structured_texts("x", "")


def test_eight_mib_serialization_boundary():
    cap = config.MAX_COMPACT_BYTES
    assert cap == 8 * 1024**2
    jobs.check_compact_size({"example": "x" * (cap - 100)})
    with pytest.raises(AlignmentResultTooLargeError):
        jobs.check_compact_size({"example": "x" * cap})


def test_text_length_failures_are_sided():
    with pytest.raises(jobs.TextTooLongError) as exc:
        jobs.compare_structured_texts("old", "new content", max_text_chars=4)
    assert exc.value.side == "new"

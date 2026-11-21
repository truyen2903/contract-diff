from app.engines.entity_extractor import extract_entities
from app.engines.entity_delta import pair_entities
from app.engines.review_priority import classify_pair


def delta(old_text, new_text):
    old = extract_entities({"node_id": "o", "own_text": old_text})
    new = extract_entities({"node_id": "n", "own_text": new_text})
    changes = [{"type": "replace", "old_span": {"start": 0, "end": len(old_text)},
                "new_span": {"start": 0, "end": len(new_text)}}]
    return old, new, pair_entities(old, new, changes)


def test_material_money_change_is_critical_and_requires_review():
    old, new, deltas = delta("100 USD", "100 VND")
    result = classify_pair("MODIFIED", "CLAUSE", False, [], deltas, old, new)
    assert result["review_priority"] == "CRITICAL"
    assert result["needs_review"] is True
    assert "CRITICAL_PRIORITY_CHANGE" in result["warnings"]


def test_high_date_change_does_not_automatically_require_review():
    old, new, deltas = delta("30 ngày", "45 ngày")
    result = classify_pair("MODIFIED", "CLAUSE", False, [], deltas, old, new)
    assert result["review_priority"] == "HIGH"
    assert result["needs_review"] is False


def test_table_is_manual_review_and_formatting_only_is_low():
    old, new, deltas = delta("100.000.000 đồng", "100.000.000 VND")
    result = classify_pair("MODIFIED", "TABLE", False, [], deltas, old, new)
    assert result["review_priority"] == "HIGH"
    assert result["needs_review"] is True
    assert "TABLE_REQUIRES_MANUAL_REVIEW" in result["warnings"]


def test_formatting_only_clause_change_is_low_without_review_warning():
    old, new, deltas = delta("100.000.000 đồng", "100.000.000 VND")
    result = classify_pair("MODIFIED", "CLAUSE", False, [], deltas, old, new)
    assert result["review_priority"] == "LOW"
    assert result["needs_review"] is False


def test_verbatim_move_is_medium():
    result = classify_pair("MOVED", "CLAUSE", False, [], [], [], [])
    assert result["review_priority"] == "MEDIUM"


def test_unchanged_ambiguous_entity_still_requires_review_on_text_edit():
    old, new, deltas = delta("100 USD (một trăm đô la); A", "100 USD (một trăm đô la); B")
    result = classify_pair("MODIFIED", "CLAUSE", False, [], deltas, old, new)
    assert result["needs_review"] is True
    assert "AMBIGUOUS_ENTITY" in result["warnings"]

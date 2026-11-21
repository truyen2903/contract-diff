from app.engines.entity_delta import pair_entities
from app.engines.entity_extractor import extract_entities


def extract(text):
    return extract_entities({"node_id": "n", "own_text": text})


def test_equal_normalized_money_with_different_currency_is_changed():
    old = extract("100.000 đồng")
    new = extract("100.000 VND")
    changes = [{"type": "replace", "old_span": {"start": 0, "end": 11}, "new_span": {"start": 0, "end": 9}}]
    deltas = pair_entities(old, new, changes)
    assert deltas[0]["signal_type"] == "MONEY_CHANGE"
    assert deltas[0]["is_value_changed"] is False


def test_repeated_duration_insertion_pairs_equal_value_before_changed_value():
    old = extract("30 ngày và 60 ngày")
    new = extract("15 ngày, 30 ngày và 90 ngày")
    changes = [
        {"type": "insert", "old_span": None, "new_span": {"start": 0, "end": 8}},
        {"type": "replace", "old_span": {"start": 12, "end": 19}, "new_span": {"start": 20, "end": 27}},
    ]
    deltas = pair_entities(old, new, changes)
    assert any(delta["old_entity"] and delta["old_entity"]["duration_value"] == "60"
               and delta["new_entity"] and delta["new_entity"]["duration_value"] == "90" for delta in deltas)
    assert any(delta["old_entity"] is None and delta["new_entity"]["duration_value"] == "15" for delta in deltas)


def test_one_sided_insertion_is_reported():
    old = extract("thanh toán")
    new = extract("thanh toán trong 30 ngày làm việc")
    deltas = pair_entities(old, new, [{"type": "insert", "old_span": None, "new_span": {"start": 13, "end": 29}}])
    assert len(deltas) == 1 and deltas[0]["pairing_status"] == "ADDED"


def test_invalid_date_edits_are_not_collapsed_to_formatting_only():
    old = extract("31/02/2025")
    new = extract("30/02/2025")
    deltas = pair_entities(old, new, [{"type": "replace", "old_span": {"start": 0, "end": 10},
                                       "new_span": {"start": 0, "end": 10}}])
    assert deltas[0]["is_value_changed"] is True


def test_percentage_context_changes_only_when_anchored_context_changes():
    old = extract("lãi suất 5%/năm trên dư nợ, trả trong 30 ngày")
    new = extract("mức lãi suất 5%/năm trên dư nợ, trả trong 30 ngày")
    changes = [{"type": "insert", "old_span": None, "new_span": {"start": 0, "end": 4}}]
    assert pair_entities(old, new, changes) == []
    changed = extract("lãi suất 5%/năm trên dư nợ thực tế, trả trong 30 ngày")
    changes = [{"type": "replace", "old_span": {"start": 23, "end": 29},
                "new_span": {"start": 23, "end": 35}}]
    assert pair_entities(old, changed, changes)[0]["is_value_changed"] is True


def test_percentage_base_ignores_previous_sentence_marker():
    old = extract("Tính trên tổng doanh thu. Lãi suất 5%/năm trên dư nợ")
    new = extract("Tính trên tổng doanh thu sửa. Lãi suất 5%/năm trên dư nợ")
    assert pair_entities(old, new, [{"type": "insert", "old_span": None, "new_span": {"start": 21, "end": 27}}]) == []

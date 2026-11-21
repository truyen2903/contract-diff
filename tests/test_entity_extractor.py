from app.engines.entity_extractor import canonical_decimal, extract_entities


def entities(text):
    return extract_entities({"node_id": "n1", "own_text": text})


def test_money_decimal_currency_alias_and_grouping():
    found = entities("Thanh toán 100.000.000 VNĐ.")
    money = next(item for item in found if item["signal_type"] == "MONEY")
    assert money["money_amount"] == "100000000"
    assert money["money_currency"] == "VND"
    assert money["is_ambiguous"] is False


def test_money_currency_change_is_not_equal_value():
    old = next(item for item in entities("100 USD") if item["signal_type"] == "MONEY")
    new = next(item for item in entities("100 VND") if item["signal_type"] == "MONEY")
    assert (old["money_amount"], old["money_currency"]) != (new["money_amount"], new["money_currency"])


def test_conflicting_spelled_amount_is_explicitly_ambiguous():
    money = next(item for item in entities("100 USD (một trăm đô la)") if item["signal_type"] == "MONEY")
    assert money["is_ambiguous"] is True
    assert money["ambiguity_reason"] == "NUMERIC_SPELLED_CONFLICT"


def test_date_duration_and_working_day_are_distinct():
    found = entities("Ngày 15 tháng 8 năm 2026, thanh toán trong 30 ngày làm việc.")
    date_entity = next(item for item in found if item["signal_type"] == "DATE")
    duration = next(item for item in found if item["signal_type"] == "DURATION")
    assert date_entity["date_iso"] == "2026-08-15"
    assert duration["calendar_type"] == "WORKING"
    calendar = next(item for item in entities("thanh toán trong 30 ngày dương lịch")
                    if item["signal_type"] == "DURATION")
    assert calendar["calendar_type"] == "CALENDAR"


def test_invalid_date_is_not_silently_coerced():
    date_entity = next(item for item in entities("ngày 31/02/2025") if item["signal_type"] == "DATE")
    assert date_entity["date_iso"] is None
    assert date_entity["is_ambiguous"] is True


def test_percentage_context_and_cross_reference():
    found = entities("Lãi 5%/năm trên dư nợ, theo Khoản 2 Điều 7.")
    percentage = next(item for item in found if item["signal_type"] == "PERCENTAGE")
    reference = next(item for item in found if item["signal_type"] == "CROSS_REF")
    assert percentage["percentage_period"] == "YEAR"
    assert reference["cross_ref_target"] == "KHOẢN 2 ĐIỀU 7"


def test_relative_reference_is_unresolved_but_has_a_real_source_span():
    reference = next(item for item in entities("Theo khoản nêu trên, Bên B giao hàng.")
                     if item["signal_type"] == "CROSS_REF")
    assert reference["evidence_scope"] == "UNRESOLVED"
    assert reference["char_end"] > reference["char_start"]
    assert any(item["evidence_scope"] == "UNRESOLVED" for item in entities("Điều này áp dụng cho khoản nói trên."))


def test_article_heading_is_not_an_internal_reference():
    found = extract_entities({"node_id": "n", "own_text": "Điều 5: Thanh toán theo Điều 6.", "body_offset": 9})
    refs = [item for item in found if item["signal_type"] == "CROSS_REF"]
    assert [item["raw_text"] for item in refs] == ["Điều 6"]


def test_modality_negation_is_a_group_transition():
    old = next(item for item in entities("Bên B có nghĩa vụ bồi thường") if item["signal_type"] == "MODALITY")
    new = next(item for item in entities("Bên B không có nghĩa vụ bồi thường") if item["signal_type"] == "MODALITY")
    assert old["modality_group"] == "OBLIGATION"
    assert new["modality_group"] == "PROHIBITION_EXEMPTION"
    needed = next(item for item in entities("Bên B không cần phải giao hàng") if item["signal_type"] == "MODALITY")
    assert needed["modality_group"] == "PROHIBITION_EXEMPTION"


def test_modality_does_not_match_party_noun():
    found = entities("Bên phải giao hàng.")
    assert not any(item["signal_type"] == "MODALITY" for item in found)


def test_canonical_decimal_is_stable():
    assert canonical_decimal("30.0") == "30"
    assert canonical_decimal("3E1") == "30"

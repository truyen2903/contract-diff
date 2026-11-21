from app.engines.legal_tokens import coalesce_changes, tokenize_legal_spans


def test_nfc_token_spans_map_back_to_original_text():
    text = "Giá a\u0301 100 USD."
    tokens = tokenize_legal_spans(text)
    assert any(token["text"] == "a\u0301" and text[token["start"]:token["end"]] == "a\u0301" for token in tokens)
    assert any(token["text"] == "100 USD" for token in tokens)


def test_legal_tokens_keep_atomic_punctuation_and_numbers():
    tokens = tokenize_legal_spans("30 ngày, 5% và 01/02/2026.")
    assert [token["text"] for token in tokens] == ["30", "ngày", ",", "5%", "và", "01/02/2026", "."]


def test_coalesce_changes_requires_whitespace_gaps_on_both_sides():
    changes = [
        {"type": "replace", "old_span": {"start": 0, "end": 1}, "new_span": {"start": 0, "end": 1}},
        {"type": "replace", "old_span": {"start": 2, "end": 3}, "new_span": {"start": 2, "end": 3}},
    ]
    merged = coalesce_changes(changes, "a b", "x y")
    assert len(merged) == 1
    assert merged[0]["old_span"] == {"start": 0, "end": 3}

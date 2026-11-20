import pytest

from app.engines.text_diff import diff_words, tokenize_with_spans


def assert_valid_spans(old_text, new_text, changes):
    # Span phải nằm trong biên, tăng dần, không chồng lấn và trỏ đúng fragment.
    for side, text in (("old", old_text), ("new", new_text)):
        previous_end = -1
        for change in changes:
            span = change[f"{side}_span"]
            if span is None:
                assert change[f"{side}_text"] == ""
                continue
            assert 0 <= span["start"] < span["end"] <= len(text)
            assert span["start"] > previous_end
            assert text[span["start"]:span["end"]] == change[f"{side}_text"]
            previous_end = span["end"]


def test_tokenize_with_spans_skips_whitespace():
    tokens = tokenize_with_spans("  Điều 1.\tGiá\n")

    assert [token["text"] for token in tokens] == ["Điều", "1.", "Giá"]
    assert tokens[0] == {"text": "Điều", "start": 2, "end": 6}


def test_equal_texts_return_no_changes():
    assert diff_words("Bên A thanh toán", "Bên A thanh toán") == []


@pytest.mark.parametrize("new_text", ["a  b", "a\nb", "  a\tb  "])
def test_whitespace_only_differences_return_no_changes(new_text):
    assert diff_words("a b", new_text) == []


def test_insert_has_no_old_span():
    changes = diff_words("a c", "a b c")

    assert changes == [{
        "type": "insert",
        "old_text": "",
        "new_text": "b",
        "old_span": None,
        "new_span": {"start": 2, "end": 3},
    }]


def test_delete_has_no_new_span():
    changes = diff_words("a b c", "a c")

    assert [(c["type"], c["old_text"], c["new_span"]) for c in changes] == [
        ("delete", "b", None),
    ]


def test_replace_vietnamese_amount():
    old_text = "Giá trị hợp đồng là 12.000.000 đồng."
    new_text = "Giá trị hợp đồng là 15.000.000 đồng."

    changes = diff_words(old_text, new_text)

    assert [(c["type"], c["old_text"], c["new_text"]) for c in changes] == [
        ("replace", "12.000.000", "15.000.000"),
    ]
    assert_valid_spans(old_text, new_text, changes)


def test_repeated_phrase_deletion_keeps_valid_spans():
    old_text = "Bên A và Bên A và Bên B"
    new_text = "Bên A và Bên B"

    changes = diff_words(old_text, new_text)

    assert [c["type"] for c in changes] == ["delete"]
    assert changes[0]["old_text"].split() == ["Bên", "A", "và"]
    assert_valid_spans(old_text, new_text, changes)


def test_reordered_clauses_are_reported_as_delete_and_insert():
    # SequenceMatcher không có nhãn MOVED: đảo khối được biểu diễn bằng xóa + chèn.
    old_text = "A B C D"
    new_text = "C D A B"

    changes = diff_words(old_text, new_text)

    assert sorted(c["type"] for c in changes) == ["delete", "insert"]
    assert_valid_spans(old_text, new_text, changes)


def test_unicode_normalization_forms_are_different_tokens():
    # Baseline không chuẩn hóa NFC/NFD; hành vi này được khóa lại có chủ đích.
    changes = diff_words("Điều 1", "Điều 1")

    assert [c["type"] for c in changes] == ["replace"]


def test_no_changes_iff_token_lists_are_equal():
    pairs = [("a b", "a  b"), ("a b", "a c"), ("", "   "), ("x", "")]
    for old_text, new_text in pairs:
        same_tokens = old_text.split() == new_text.split()
        assert (diff_words(old_text, new_text) == []) == same_tokens

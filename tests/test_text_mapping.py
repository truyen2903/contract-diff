from app.engines.text_mapping import build_document_text, span_to_page_locations


def make_pages(*texts, first_page=1):
    return [
        {"page_number": first_page + index, "text": text, "warnings": []}
        for index, text in enumerate(texts)
    ]


def test_pages_are_joined_with_separator():
    data = build_document_text(make_pages("abc", "def"))

    assert data["fulltext"] == "abc\n\ndef"
    assert data["page_ranges"] == [
        {"page_number": 1, "start": 0, "end": 3},
        {"page_number": 2, "start": 5, "end": 8},
    ]


def test_empty_page_list():
    assert build_document_text([]) == {"fulltext": "", "page_ranges": []}


def test_separator_depends_on_position_not_page_number():
    # Danh sách trang con bắt đầu từ trang 2 không được có separator thừa ở đầu.
    data = build_document_text(make_pages("abc", "def", first_page=2))

    assert data["fulltext"] == "abc\n\ndef"
    assert data["page_ranges"][0] == {"page_number": 2, "start": 0, "end": 3}


def test_duplicate_page_numbers_still_get_separator():
    pages = make_pages("abc", "def")
    pages[1]["page_number"] = 1

    assert build_document_text(pages)["fulltext"] == "abc\n\ndef"


def test_empty_middle_page_keeps_empty_range():
    data = build_document_text(make_pages("A", "", "B"))

    assert data["fulltext"] == "A\n\n\n\nB"
    assert data["page_ranges"][1] == {"page_number": 2, "start": 3, "end": 3}


def test_span_none_has_no_locations():
    assert span_to_page_locations(None, []) == []


def test_span_across_pages_is_split_per_page():
    data = build_document_text(make_pages("one two three", "four five"))
    start = data["fulltext"].index("three")
    end = data["fulltext"].index("four") + len("four")

    locations = span_to_page_locations({"start": start, "end": end}, data["page_ranges"])

    assert locations == [
        {"page_number": 1, "start": 8, "end": 13},
        {"page_number": 2, "start": 0, "end": 4},
    ]


def test_span_across_empty_page_skips_it():
    data = build_document_text(make_pages("A", "", "B"))

    locations = span_to_page_locations({"start": 0, "end": 7}, data["page_ranges"])

    assert [location["page_number"] for location in locations] == [1, 3]


def test_span_inside_separator_has_no_locations():
    data = build_document_text(make_pages("A", "B"))

    assert span_to_page_locations({"start": 1, "end": 3}, data["page_ranges"]) == []

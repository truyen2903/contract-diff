def build_document_text(pages: list[dict]) -> dict:
    fulltext = ""
    page_ranges = []
    start = 0
    for page in pages:
        separator = "\n\n" if page_ranges else ""
        start += len(separator)
        fulltext += separator + page["text"]
        end = start + len(page["text"])
        page_ranges.append({
            "page_number": page["page_number"],
            "start": start,
            "end": end,
        })
        start = end
    return {"fulltext": fulltext, "page_ranges": page_ranges}

def span_to_page_locations(
    span: dict | None,
    page_ranges: list[dict]) -> list[dict]:
    if span is None:
        return []
    locations = []
    for page in page_ranges:
        overlap_start = max(span["start"], page["start"])
        overlap_end = min(span["end"], page["end"])

        if overlap_start >= overlap_end:
            continue

        locations.append({
            "page_number": page["page_number"],
            "start": overlap_start - page["start"],
            "end": overlap_end - page["start"],
        })
    return locations

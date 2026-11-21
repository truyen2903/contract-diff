"""Deterministic legal token spans used by B3 experiments.

The B2 ``word_changes`` stream remains the validated change stream.  These
tokens are an additional, offset-preserving view for semantic tooling.
"""

import re
import unicodedata


_TOKEN_RE = re.compile(
    r"(?:\d{1,4}[/-]\d{1,2}[/-]\d{1,4}|\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})"
    r"|(?:\d+(?:[.,]\d+)*(?:\s*(?:%|‰)))"
    r"|(?:\d+(?:[.,]\d+)*(?:\s*(?:VND|VNĐ|USD|EUR|JPY|đồng|đ)))"
    r"|(?:\d+(?:[.,]\d+)*)"
    r"|(?:[\wÀ-ỹ]+(?:[-'][\wÀ-ỹ]+)*)"
    r"|(?:[^\w\s])",
    re.IGNORECASE,
)


def _normal_view(text):
    normalized = []
    starts = []
    ends = []
    index = 0
    while index < len(text):
        start = index
        index += 1
        while index < len(text) and unicodedata.combining(text[index]):
            index += 1
        chunk = text[start:index]
        chunk = chunk.replace("\u00a0", " ").replace("\ufeff", " ")
        value = unicodedata.normalize("NFC", chunk)
        for char in value:
            normalized.append(char)
            starts.append(start)
            ends.append(index)
    return "".join(normalized), starts, ends


def tokenize_legal_spans(text):
    """Return atomic legal token dictionaries with original code-point spans."""
    view, starts, ends = _normal_view(text)
    tokens = []
    for match in _TOKEN_RE.finditer(view):
        start, end = match.span()
        original_start = starts[start]
        original_end = ends[end - 1]
        raw = text[original_start:original_end]
        tokens.append({"text": raw, "start": original_start, "end": original_end,
                       "kind": "PUNCT" if not match.group().strip().isalnum() else "WORD",
                       "normalized": unicodedata.normalize("NFC", raw).replace("\u00a0", " ")})
    return tokens


def _gap_is_whitespace(text, start, end):
    return not text[start:end].strip()


def coalesce_changes(changes, old_text, new_text):
    """Merge adjacent opcodes when both intervening gaps contain whitespace only."""
    if not changes:
        return []
    result = []
    for change in changes:
        item = {"type": change["type"],
                "old_span": dict(change["old_span"]) if change.get("old_span") else None,
                "new_span": dict(change["new_span"]) if change.get("new_span") else None}
        if not result:
            result.append(item)
            continue
        previous = result[-1]
        old_previous_end = previous["old_span"]["end"] if previous["old_span"] else None
        old_start = item["old_span"]["start"] if item["old_span"] else None
        new_previous_end = previous["new_span"]["end"] if previous["new_span"] else None
        new_start = item["new_span"]["start"] if item["new_span"] else None
        old_gap_ok = ((old_previous_end is None and old_start is None)
                      or (old_previous_end is not None and old_start is not None
                          and _gap_is_whitespace(old_text, old_previous_end, old_start)))
        new_gap_ok = ((new_previous_end is None and new_start is None)
                      or (new_previous_end is not None and new_start is not None
                          and _gap_is_whitespace(new_text, new_previous_end, new_start)))
        if old_gap_ok and new_gap_ok:
            if previous["old_span"] and item["old_span"]:
                previous["old_span"]["end"] = item["old_span"]["end"]
            elif item["old_span"]:
                previous["old_span"] = dict(item["old_span"])
            if previous["new_span"] and item["new_span"]:
                previous["new_span"]["end"] = item["new_span"]["end"]
            elif item["new_span"]:
                previous["new_span"] = dict(item["new_span"])
            if previous["old_span"] and previous["new_span"]:
                previous["type"] = "replace"
            elif previous["old_span"]:
                previous["type"] = "delete"
            else:
                previous["type"] = "insert"
        else:
            result.append(item)
    return result

"""Bounded, conservative semantic extraction for a compact alignment node."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from app.core import config
from app.engines.alignment_budget import AlignmentResultTooLargeError


_MONEY = re.compile(
    r"(?P<number>\d[\d.,]*)(?:\s*(?P<scale>tỷ|triệu|nghìn|ngàn))?\s*"
    r"(?P<currency>VNĐ|VND|đồng|đ|USD|EUR|JPY)\b",
    re.IGNORECASE,
)
_DATE_NUMERIC = re.compile(r"\b(?P<day>\d{1,2})[/-](?P<month>\d{1,2})[/-](?P<year>\d{4})\b")
_DATE_WORDS = re.compile(r"\bngày\s+(?P<day>\d{1,2})\s+tháng\s+(?P<month>\d{1,2})\s+năm\s+(?P<year>\d{4})\b", re.I)
_PERCENT = re.compile(
    r"(?P<rate>\d+(?:[.,]\d+)?)\s*(?:%|phần\s+trăm)"
    r"(?:\s*/\s*(?P<slash>ngày|tháng|năm))?"
    r"(?:\s*(?:mỗi|theo)\s+(?P<each>ngày|tháng|năm))?",
    re.I,
)
_DURATION = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>giờ|ngày|tuần|tháng|năm)"
    r"(?:\s+(?P<calendar>lịch|dương\s+lịch|theo\s+lịch|làm\s+việc|làm\s+các\s+ngày))?",
    re.I,
)
_CROSS_REF = re.compile(
    r"\b(?:điểm\s+[a-z]\s+)?(?:khoản\s+\d+\s+)?điều\s+\d+(?:\.\d+)?|"
    r"\b(?:khoản|điểm|điều)\s+(?:nêu\s+trên|nói\s+trên|này|trên\s+đây)\b",
    re.I,
)

_MODALITY = (
    ("PROHIBITION_EXEMPTION", re.compile(r"\bkhông\s+cần\s+phải\b|\bchưa\s+phải\b|\bkhông\s+được\b|\bkhông\s+có\s+quyền\b|\bkhông\s+có\s+nghĩa\s+vụ\b|\bkhông\s+phải\b|\bkhông\s+chịu\s+trách\s+nhiệm\b|\bđược\s+miễn\b", re.I)),
    ("OBLIGATION", re.compile(r"\bcó\s+nghĩa\s+vụ\b|\bphải\b|\bcam\s+kết\b|\bchịu\s+trách\s+nhiệm\b", re.I)),
    ("PERMISSION", re.compile(r"\bđược\s+quyền\b|\bđược\s+phép\b|\bcó\s+quyền\b", re.I)),
)
_CURRENCY = {"vnđ": "VND", "vnd": "VND", "đồng": "VND", "đ": "VND",
             "usd": "USD", "eur": "EUR", "jpy": "JPY"}
_UNIT = {"giờ": "HOUR", "ngày": "DAY", "tuần": "WEEK", "tháng": "MONTH", "năm": "YEAR"}
_SCALE = {"nghìn": Decimal("1000"), "ngàn": Decimal("1000"), "triệu": Decimal("1000000"), "tỷ": Decimal("1000000000")}
_NUMBER_WORD = re.compile(r"\b(?:một|hai|ba|bốn|tư|năm|sáu|bảy|tám|chín|mười|trăm|nghìn|triệu|tỷ)\b", re.I)


def _decimal(raw):
    value = raw.replace(" ", "")
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind(".") and len(value.rsplit(",", 1)[1]) <= 2:
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "").replace(".", "")
    elif "," in value:
        tail = value.rsplit(",", 1)[1]
        value = value.replace(",", ".") if len(tail) <= 2 else value.replace(",", "")
    elif value.count(".") > 1:
        value = value.replace(".", "")
    elif "." in value and len(value.rsplit(".", 1)[1]) == 3:
        value = value.replace(".", "")
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def canonical_decimal(value):
    """Return a stable fixed-point Decimal representation for the JSON boundary."""
    decimal = value if isinstance(value, Decimal) else Decimal(str(value))
    rendered = format(decimal, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _calendar(value):
    if not value:
        return "UNSPECIFIED"
    return "WORKING" if value.lower().startswith("làm") else "CALENDAR"


def _evidence(node, start, end):
    segments = node.get("source_segments") or []
    evidence = []
    for segment in segments:
        if segment["own_end"] <= start or segment["own_start"] >= end:
            continue
        left = max(start, segment["own_start"]) - segment["own_start"]
        right = min(end, segment["own_end"]) - segment["own_start"]
        exact = segment.get("raw_exact", False)
        evidence.append({"page": segment["page"], "clean_start": segment["clean_start"] + left,
                         "clean_end": segment["clean_start"] + right, "raw_exact": exact,
                         "raw_start": segment["raw_start"] + left if exact else segment["raw_start"],
                         "raw_end": segment["raw_start"] + right if exact else segment["raw_end"],
                         "source_node_id": node.get("node_id")})
    if not evidence:
        evidence.append({"page": 1, "clean_start": start, "clean_end": end, "raw_start": start,
                         "raw_end": end, "raw_exact": False, "source_node_id": node.get("node_id")})
    return evidence


def _entity(node, signal_type, match, **values):
    start, end = match.span()
    return _entity_at(node, signal_type, start, end, **values)


def _entity_at(node, signal_type, start, end, **values):
    raw = node["own_text"][start:end]
    return {"entity_id": f"{signal_type.lower()}-{start}-{end}", "signal_type": signal_type,
            "raw_text": raw, "char_start": start, "char_end": end,
            "source_evidence": _evidence(node, start, end), **values}


def _overlaps(start, end, entities):
    return any(start < item["char_end"] and item["char_start"] < end for item in entities)


def _date_entity(node, match, claimed):
    day, month, year = (int(match.group(name)) for name in ("day", "month", "year"))
    try:
        iso = date(year, month, day).isoformat()
        ambiguous, reason = False, None
    except ValueError:
        iso, ambiguous, reason = None, True, "INVALID_DATE"
    item = _entity(node, "DATE", match, date_iso=iso, is_ambiguous=ambiguous, ambiguity_reason=reason,
                   normalized_value=iso)
    claimed.append(item)
    return item


def extract_entities(node, parent=None, *, max_entities=config.MAX_B3_ENTITIES_PER_NODE):
    """Extract explicit entities and optional inherited modality evidence.

    Returned values are plain dictionaries so the worker can serialize them before
    the parent process performs strict schema validation.
    """
    text = node.get("own_text", "")
    entities = []
    claimed = []

    def add(item):
        if not _overlaps(item["char_start"], item["char_end"], claimed):
            claimed.append(item)
            entities.append(item)
            if len(entities) > max_entities:
                raise AlignmentResultTooLargeError("B3 entity limit exceeded")

    for matcher in (_DATE_WORDS, _DATE_NUMERIC):
        for match in matcher.finditer(text):
            if not _overlaps(*match.span(), claimed):
                add(_date_entity(node, match, []))

    for match in _MONEY.finditer(text):
        number = match.group("number")
        value = _decimal(number)
        if value is None:
            continue
        scale = match.group("scale")
        if scale:
            value *= _SCALE[scale.lower()]
        raw_currency = match.group("currency")
        ambiguity = None
        if not scale and ((number.count(".") == 1 and "," not in number and len(number.rsplit(".", 1)[1]) == 3)
                          or (number.count(",") == 1 and "." not in number and len(number.rsplit(",", 1)[1]) == 3)):
            ambiguity = "GROUPING_SEPARATOR_AMBIGUOUS"
        tail = text[match.end():match.end() + 24]
        spelled_match = re.search(r"\s*\([^)]*(?:\b(?:một|hai|ba|bốn|tư|năm|sáu|bảy|tám|chín|mười|trăm|nghìn|triệu|tỷ)\b)[^)]*\)|\bbằng\s+chữ\b[^.;\n]*", tail, re.I)
        spelled = spelled_match.group(0) if spelled_match else None
        item = _entity(node, "MONEY", match, money_amount=canonical_decimal(value),
                       money_currency=_CURRENCY[raw_currency.lower()], money_numeric_raw=number,
                       money_spelled_raw=spelled,
                       normalized_value=f"{canonical_decimal(value)} {_CURRENCY[raw_currency.lower()]}",
                       is_ambiguous=bool(ambiguity or spelled),
                       ambiguity_reason=ambiguity or ("NUMERIC_SPELLED_CONFLICT" if spelled else None))
        add(item)

    for match in _PERCENT.finditer(text):
        if _overlaps(*match.span(), claimed):
            continue
        rate = _decimal(match.group("rate"))
        if rate is None:
            continue
        period = {"ngày": "DAY", "tháng": "MONTH", "năm": "YEAR"}.get(
            (match.group("slash") or match.group("each") or "").lower(), "NONE")
        before = text[max(0, match.start() - 70):match.start()]
        after = text[match.end():min(len(text), match.end() + 70)]
        base_match = re.search(r"\btrên\s+([^,.;]+)", after, re.I)
        cap_match = re.search(r"\b(?:tối đa|không quá)\s+([^,.;]+)", after, re.I) or re.search(
            r"\b(?:tối đa|không quá)\s+([^,.;]+)", before, re.I)
        trigger_match = re.search(r"\b(?:khi|sau khi|trễ hạn|quá hạn)\s+([^,.;]+)", after, re.I) or re.search(
            r"\b(?:khi|sau khi|trễ hạn|quá hạn)\s+([^,.;]+)", before, re.I)
        add(_entity(node, "PERCENTAGE", match, percentage_rate=canonical_decimal(rate),
                    percentage_period=period, percentage_base=base_match.group(1).strip() if base_match else None,
                    percentage_cap=cap_match.group(1).strip() if cap_match else None,
                    percentage_trigger=trigger_match.group(1).strip() if trigger_match else None,
                    normalized_value=f"{canonical_decimal(rate)} {period}"))

    for match in _DURATION.finditer(text):
        if _overlaps(*match.span(), claimed):
            continue
        value = _decimal(match.group("value"))
        if value is None:
            continue
        unit = _UNIT[match.group("unit").lower()]
        add(_entity(node, "DURATION", match, duration_value=canonical_decimal(value), duration_unit=unit,
                    calendar_type=_calendar(match.group("calendar")),
                    normalized_value=f"{canonical_decimal(value)} {unit} {_calendar(match.group('calendar'))}"))

    for group, matcher in _MODALITY:
        for match in matcher.finditer(text):
            if _overlaps(*match.span(), claimed):
                continue
            # ``bên phải`` is a party noun, not a modality phrase.
            if group == "OBLIGATION" and text[max(0, match.start() - 5):match.start()].lower().endswith("bên "):
                continue
            add(_entity(node, "MODALITY", match, modality_group=group, normalized_value=group))

    reference_start = node.get("body_offset", 0)
    for match in _CROSS_REF.finditer(text[reference_start:]):
        start, end = match.start() + reference_start, match.end() + reference_start
        if _overlaps(start, end, claimed):
            continue
        raw = match.group(0)
        lowered = raw.lower()
        unresolved = any(term in lowered for term in ("nêu trên", "nói trên", "này", "trên đây"))
        target = None if unresolved else " ".join(raw.split()).upper()
        add(_entity_at(node, "CROSS_REF", start, end, cross_ref_target=target,
                    normalized_value=target, evidence_scope="UNRESOLVED" if unresolved else "EXPLICIT",
                    is_ambiguous=unresolved, ambiguity_reason="RELATIVE_REFERENCE" if unresolved else None))

    if not any(item["signal_type"] == "MODALITY" for item in entities) and parent:
        for group, matcher in _MODALITY:
            match = matcher.search(parent.get("own_text", ""))
            if match:
                entities.append({"entity_id": f"inherited-{group.lower()}-{node.get('node_id', 'node')}",
                                 "signal_type": "MODALITY", "raw_text": match.group(0), "char_start": 0,
                                 "char_end": 0, "normalized_value": group, "modality_group": group,
                                 "evidence_scope": "INHERITED", "context_source_node_id": parent.get("node_id"),
                                 "source_evidence": _evidence(parent, *match.span())})
                break
    return sorted(entities, key=lambda item: (item["char_start"], item["char_end"], item["entity_id"]))

"""Bounded, deterministic pairing of semantic entities across one alignment edge."""

from decimal import Decimal

from app.core import config
from app.engines.alignment_budget import AlignmentResultTooLargeError


_SIGNAL = {"MONEY": "MONEY_CHANGE", "DATE": "DATE_DURATION_CHANGE", "DURATION": "DATE_DURATION_CHANGE",
           "PERCENTAGE": "PERCENTAGE_CHANGE", "MODALITY": "MODALITY_SIGNAL_CHANGE", "CROSS_REF": "CROSS_REF_CHANGE"}


def _key(entity):
    kind = entity["signal_type"]
    if kind == "MONEY":
        return kind, entity.get("money_amount"), entity.get("money_currency"), entity.get("money_spelled_raw")
    if kind == "DATE":
        return kind, entity.get("date_iso") if not entity.get("is_ambiguous") else entity.get("raw_text"), entity.get("is_ambiguous")
    if kind == "DURATION":
        return kind, entity.get("duration_value"), entity.get("duration_unit"), entity.get("calendar_type")
    if kind == "PERCENTAGE":
        return kind, entity.get("percentage_rate"), entity.get("percentage_period"), entity.get("percentage_base"), entity.get("percentage_cap"), entity.get("percentage_trigger")
    if kind == "MODALITY":
        return kind, entity.get("modality_group")
    return kind, entity.get("cross_ref_target"), entity.get("is_ambiguous")


def _intersects(entity, span):
    if not span or entity["char_start"] == entity["char_end"]:
        return False
    return entity["char_start"] < span["end"] and span["start"] < entity["char_end"]


def _change_index(entity, changes, side):
    field = side + "_span"
    for index, change in enumerate(changes):
        if _intersects(entity, change.get(field)):
            return index
    return None


def _summary(old, new, status):
    left = old["raw_text"] if old else "<deleted>"
    right = new["raw_text"] if new else "<added>"
    return f"{status}: {left} -> {right}"


def _delta(old, new, status):
    kind = (old or new)["signal_type"]
    value_changed = status != "FORMATTING_ONLY"
    pairing = {"FORMATTING_ONLY": "PAIRED", "CHANGED": "PAIRED"}.get(status, status)
    return {"signal_type": _SIGNAL[kind], "old_entity": old, "new_entity": new,
            "is_value_changed": value_changed, "summary": _summary(old, new, status),
            "pairing_status": pairing}


def pair_entities(old_entities, new_entities, changes, *, max_candidates=config.MAX_B3_PAIR_CANDIDATES):
    """Pair entities with exact cancellation before changed-span matching.

    This avoids positional mispairing when an equal entity is inserted before a
    genuinely changed repeated value. Inherited context is retained on the row
    but excluded from semantic transitions because it has no child span.
    """
    old = [e for e in old_entities if e.get("evidence_scope") != "INHERITED"]
    new = [e for e in new_entities if e.get("evidence_scope") != "INHERITED"]
    if not changes:
        return []
    if len(old) * len(new) > max_candidates:
        raise AlignmentResultTooLargeError("B3 entity pairing limit exceeded")
    used_old, used_new, result = set(), set(), []
    # Exact normalized values are paired independent of position.
    for i, left in enumerate(old):
        if i in used_old:
            continue
        matches = [j for j, right in enumerate(new) if j not in used_new and _key(left) == _key(right)]
        if matches:
            j = min(matches, key=lambda index: (abs(new[index]["char_start"] - left["char_start"]), index))
            used_old.add(i)
            used_new.add(j)
            right = new[j]
            if left["raw_text"] != right["raw_text"]:
                result.append(_delta(left, right, "FORMATTING_ONLY"))

    remaining_old = [i for i in range(len(old)) if i not in used_old]
    remaining_new = [j for j in range(len(new)) if j not in used_new]
    while remaining_old and remaining_new:
        best = None
        for i in remaining_old:
            for j in remaining_new:
                if old[i]["signal_type"] != new[j]["signal_type"]:
                    continue
                old_index = _change_index(old[i], changes, "old")
                new_index = _change_index(new[j], changes, "new")
                score = (0 if old_index is not None and old_index == new_index else 1,
                         abs((old_index if old_index is not None else len(changes)) -
                             (new_index if new_index is not None else len(changes))),
                         abs(old[i]["char_start"] - new[j]["char_start"]), i, j)
                if best is None or score < best[0]:
                    best = (score, i, j)
        if best is None:
            break
        _, i, j = best
        remaining_old.remove(i)
        remaining_new.remove(j)
        used_old.add(i)
        used_new.add(j)
        result.append(_delta(old[i], new[j], "CHANGED"))
    for i in remaining_old:
        result.append(_delta(old[i], None, "DELETED"))
    for j in remaining_new:
        result.append(_delta(None, new[j], "ADDED"))
    return sorted(result, key=lambda item: ((item["old_entity"] or item["new_entity"])["signal_type"],
                                             (item["old_entity"] or {"char_start": -1})["char_start"],
                                             (item["new_entity"] or {"char_start": -1})["char_start"]))

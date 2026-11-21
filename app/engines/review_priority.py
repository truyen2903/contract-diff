"""Single, auditable B3 review-priority decision table."""


def classify_pair(category, node_type, parent_changed, warnings, deltas, old_entities, new_entities,
                  *, parent_status=None):
    signals = {delta["signal_type"] for delta in deltas}
    if any(not delta["is_value_changed"] for delta in deltas):
        signals.add("FORMATTING_ONLY")
    reasons = []
    resulting_warnings = set(warnings)
    critical = False
    high = False

    for delta in deltas:
        if delta["signal_type"] in {"MONEY_CHANGE", "PERCENTAGE_CHANGE", "MODALITY_SIGNAL_CHANGE"}:
            if delta["is_value_changed"] or any(
                    entity and entity.get("is_ambiguous") for entity in (delta.get("old_entity"), delta.get("new_entity"))):
                critical = True
                reasons.append(delta["signal_type"] + "_MATERIAL")
        elif delta["signal_type"] == "DATE_DURATION_CHANGE" and delta["is_value_changed"]:
            high = True
            reasons.append("DATE_OR_DURATION_CHANGE")
        elif delta["signal_type"] == "CROSS_REF_CHANGE":
            high = True
            reasons.append("INTERNAL_CROSS_REFERENCE_RISK")
            resulting_warnings.add("INTERNAL_CROSS_REFERENCE_RISK")

    if category in ("ADDED", "DELETED") and node_type == "ARTICLE":
        critical = True
        reasons.append("ARTICLE_ADD_DELETE")
    elif category in ("ADDED", "DELETED") and node_type in ("CLAUSE", "TABLE"):
        high = True
        reasons.append("CLAUSE_OR_TABLE_ADD_DELETE")
    if category == "MOVED_AND_MODIFIED":
        high = True
        reasons.append("MOVED_AND_MODIFIED")
    if parent_changed or parent_status == "CHANGED":
        high = True
        reasons.append("PARENT_CHANGE_REQUIRES_REVIEW")
        resulting_warnings.add("PARENT_CHANGE_REQUIRES_REVIEW")
    if node_type == "TABLE":
        high = True
        reasons.append("TABLE_REQUIRES_MANUAL_REVIEW")
        resulting_warnings.add("TABLE_REQUIRES_MANUAL_REVIEW")
    delta_entities = [entity for delta in deltas for entity in (delta.get("old_entity"), delta.get("new_entity")) if entity]
    direct_entities = [entity for entity in old_entities + new_entities if entity.get("evidence_scope") != "INHERITED"]
    if any(entity.get("is_ambiguous") for entity in direct_entities):
        high = True
        reasons.append("AMBIGUOUS_ENTITY")
        resulting_warnings.add("AMBIGUOUS_ENTITY")

    if critical:
        priority = "CRITICAL"
        resulting_warnings.add("CRITICAL_PRIORITY_CHANGE")
        reasons.append("CRITICAL_PRIORITY_CHANGE")
    elif high:
        priority = "HIGH"
    elif deltas and all(not delta["is_value_changed"] for delta in deltas):
        priority = "LOW"
    elif category in ("MODIFIED", "MOVED_AND_MODIFIED", "MOVED") and deltas:
        priority = "MEDIUM"
    elif category == "MODIFIED":
        priority = "MEDIUM"
        signals.add("TEXT_EDIT")
        reasons.append("TEXT_EDIT")
    else:
        priority = "LOW"

    if category == "MOVED" and not deltas:
        priority = "MEDIUM"
        signals.add("TEXT_EDIT")
        reasons.append("VERBATIM_MOVE")
    if category in ("MODIFIED", "MOVED_AND_MODIFIED") and not deltas:
        signals.add("TEXT_EDIT")
    needs_review = bool(resulting_warnings)
    return {"review_priority": priority, "needs_review": needs_review,
            "semantic_signals": sorted(signals), "review_reasons": sorted(set(reasons)),
            "warnings": sorted(resulting_warnings)}

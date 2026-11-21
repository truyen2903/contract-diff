"""Hierarchical alignment. Node IDs are local to their respective document."""

from collections import Counter, defaultdict

from app.core.config import MAX_STRUCTURE_NODES
from app.engines.alignment_budget import AlignmentBudget, StructureTooLargeError
from app.engines.assignment import solve_assignment
from app.engines.similarity import (body_start, combine_scores, content_key, fit_lexical,
                                    lexical_similarity, position_similarity, title_similarity, unique_anchors)
from app.engines.text_diff import tokenize_with_spans


ALIGNMENT_CONFIG = {
    "tau_min": .40, "tau_lex_floor": .15, "tau_orphan": .60, "tau_high": .65,
    "delta_margin": .08, "edge_penalty_alpha": 0.0, "one_sided_title": "omit",
    "move_convention": "v2-4.3-zero-based-v1",
}
ARTICLE = "STAGE1_ARTICLE"
LOCAL = "STAGE1_INTRA_CLAUSE"
ORPHAN = "STAGE2_ORPHAN_CLAUSE"
BLOCK = "STAGE1_BLOCK"
ANCHOR = "EXACT_ANCHOR"
BLOCK_TYPES = ("PREAMBLE", "PARAGRAPH", "SIGNATURE", "TABLE")


def validate_config(config):
    if config.keys() != ALIGNMENT_CONFIG.keys():
        raise ValueError("unknown alignment configuration")
    if not (0 <= config["edge_penalty_alpha"] < min(config["tau_min"], config["tau_orphan"])
            and max(config["tau_min"], config["tau_orphan"]) <= 1
            and config["tau_min"] <= config["tau_high"] <= 1
            and 0 <= config["delta_margin"] <= 1 and 0 <= config["tau_lex_floor"] <= 1
            and config["one_sided_title"] in ("omit", "half", "zero")
            and config["move_convention"] == ALIGNMENT_CONFIG["move_convention"]):
        raise ValueError("invalid alignment configuration")


def prepare(nodes, side):
    if len(nodes) > MAX_STRUCTURE_NODES:
        error = StructureTooLargeError(f"{len(nodes)} > {MAX_STRUCTURE_NODES}")
        error.side = side
        raise error
    by_id = {}
    children = defaultdict(list)
    for node in nodes:
        key = node["node_id"]
        kind = node["node_type"]
        if not isinstance(key, str) or not key or key in by_id or kind not in ("ARTICLE", "CLAUSE", *BLOCK_TYPES):
            raise ValueError(f"{side}: invalid node {key}")
        if (kind == "CLAUSE") != (node["parent_id"] is not None):
            raise ValueError(f"{side}: invalid parent of {key}")
        if kind == "CLAUSE":
            children[node["parent_id"]].append(key)
        offset, warning = body_start(node["own_text"], node["number_label"])
        body = node["own_text"][offset:]
        by_id[key] = {**node, "key": content_key(body), "body_warning": warning,
                      "tokens": [t["text"] for t in tokenize_with_spans(body)]}
    for key, node in by_id.items():
        if node["children"] != children.get(key, []):
            raise ValueError(f"{side}: inconsistent children of {key}")
        if node["node_type"] == "CLAUSE":
            parent = by_id.get(node["parent_id"])
            if parent is None or parent["node_type"] != "ARTICLE":
                raise ValueError(f"{side}: dangling clause parent")
        elif node["children"]:
            parts = (node["key"], *(by_id[c]["key"] for c in node["children"]))
            node["anchor_key"] = parts
            node["key"] = content_key(" ".join(parts))
    return by_id


def weighted_lis(edges, m, n):
    edges = sorted(edges)
    objectives = [None] * len(edges)
    following = [None] * len(edges)
    best = None
    for r in reversed(range(len(edges))):
        i, j, weight = edges[r]
        tail = (0, 0, 0)
        for s in range(r + 1, len(edges)):
            if edges[s][1] > j and objectives[s] > tail:
                tail = objectives[s]
                following[r] = s
        objectives[r] = (weight + tail[0], 1 + tail[1], tail[2] - abs(i*n - j*m))
        # Equal objective chooses the earliest old start; successors were scanned in old order.
        if best is None or objectives[r] >= objectives[best]:
            best = r
    stable = set()
    while best is not None:
        stable.add(edges[best][:2])
        best = following[best]
    return stable


class MatchingLevel:
    """One shared corpus per node type. Scores retain the scope in which they were computed."""

    def __init__(self, old, new, config, budget, observe=None):
        self.old, self.new = old, new
        self.config, self.budget = config, budget
        self.observe = observe
        self.old_keys, self.new_keys = list(old), list(new)
        self.left_counts = Counter(n["key"] for n in old.values())
        self.right_counts = Counter(n["key"] for n in new.values())
        self.matches = {}
        self.scores = defaultdict(dict)
        self.reverse = defaultdict(dict)
        self.vectors = None
        anchors = unique_anchors([n.get("anchor_key", n["key"]) for n in old.values()],
                                 [n.get("anchor_key", n["key"]) for n in new.values()])
        for i, j in anchors:
            u, v = self.old_keys[i], self.new_keys[j]
            self.matches[u] = (v, 1.0, ANCHOR)
            if observe:
                observe("anchor", [u], [v], None)

    def score(self, u, v, position, stage):
        if self.vectors is None:
            both = [*self.old.values(), *self.new.values()]
            self.budget.charge("score_work", sum(4 * len(n["key"]) for n in both), "vectorization")
            vectors = fit_lexical([node["key"] for node in both])
            split = len(self.old)
            self.vectors = (dict(zip(self.old, vectors[:split])), dict(zip(self.new, vectors[split:])))
        x, y = self.vectors[0][u], self.vectors[1][v]
        a, b = self.old[u]["title"], self.new[v]["title"]
        work = min(len(x[1]), len(y[1])) + min(len(x[2]), len(y[2]))
        if a and b and a != b:
            work += len(a) * len(b)
        self.budget.charge("score_work", work, stage)
        lex = lexical_similarity(x, y)
        title = title_similarity(a, b, self.config["one_sided_title"])
        return combine_scores(lex, title, position), lex

    def assign(self, left, right, stage):
        if not left or not right:
            return
        # Reuse same-parent scores in recovery. Count before building the dense matrix.
        right_ids = set(right)
        cached = sum(
            sum(1 for v in right_ids.intersection(self.scores[u])
                if self.scores[u][v][3] == stage)
            for u in left
        )
        fixed_new = {v for v, _, _ in self.matches.values()}
        free_left = [u for u in left if u not in self.matches]
        free_right = [v for v in right if v not in fixed_new]
        if self.observe:
            self.observe("structure", free_left, free_right, None)
        self.budget.charge("pairs", len(left) * len(right) - cached, stage)
        old_pos = {u: i for i, u in enumerate(left)}
        new_pos = {v: j for j, v in enumerate(right)}
        cfg = self.config
        for i, u in enumerate(left):
            for j, v in enumerate(right):
                if v in self.scores[u] and (stage != ORPHAN or self.scores[u][v][3] == ORPHAN):
                    continue
                position = None if stage == ORPHAN else position_similarity(i, len(left), j, len(right))
                score, lex = self.score(u, v, position, stage)
                threshold = cfg["tau_orphan"] if stage == ORPHAN else cfg["tau_min"]
                entry = (score, lex >= cfg["tau_lex_floor"], threshold, stage)
                self.scores[u][v] = self.reverse[v][u] = entry
        matrix = []
        for u in free_left:
            row = []
            for v in free_right:
                score, eligible, threshold, _ = self.scores[u][v]
                row.append(score if eligible and score >= threshold else None)
            matrix.append(row)
        if stage == ORPHAN:
            old_pos = {u: i for i, u in enumerate(self.old_keys)}
            new_pos = {v: j for j, v in enumerate(self.new_keys)}
        pairs = solve_assignment(matrix, min(cfg["tau_min"], cfg["tau_orphan"]), cfg["edge_penalty_alpha"],
                                 old_pos=[old_pos[u] for u in free_left], new_pos=[new_pos[v] for v in free_right],
                                 scope=(len(old_pos), len(new_pos)), old_keys=[self.old[u]["key"] for u in free_left],
                                 new_keys=[self.new[v]["key"] for v in free_right], budget=self.budget, stage=stage)
        if self.observe:
            self.observe("scored", free_left, free_right, self.scores)
        for i, j in pairs:
            u, v = free_left[i], free_right[j]
            score, _, _, selected_stage = self.scores[u][v]
            self.matches[u] = (v, score, selected_stage)

    def alternatives(self, u, v):
        candidates = []
        for side, options, partner in (("new", self.scores.get(u, {}), v),
                                       ("old", self.reverse.get(v, {}), u)):
            for other, (score, eligible, threshold, _) in options.items():
                if other == partner or not eligible:
                    continue
                if (u is None or v is None) and score < threshold - self.config["delta_margin"]:
                    continue
                candidates.append({"candidate_side": side, "node_id": other, "score": score})
        return sorted(candidates, key=lambda c: (-c["score"], c["candidate_side"], c["node_id"]))[:2]

    def recover(self):
        for u, (v, score, stage) in list(self.matches.items()):
            if stage != LOCAL:
                continue
            alternatives = self.alternatives(u, v)
            runner_up = alternatives[0]["score"] if alternatives else 0
            if score < self.config["tau_high"] or score - runner_up < self.config["delta_margin"]:
                del self.matches[u]
        fixed_new = {v for v, _, _ in self.matches.values()}
        left = [u for u in self.old if u not in self.matches]
        right = [v for v in self.new if v not in fixed_new]
        fixed_old = list(self.matches)
        self.assign(left, right, ORPHAN)
        # Retained matches compete for confidence but cannot be reassigned.
        self.assign(left, [v for v in self.new if v in fixed_new], ORPHAN)
        self.assign(fixed_old, right, ORPHAN)

    def moved(self, left, right):
        target = {v: j for j, v in enumerate(right)}
        edges = []
        for i, u in enumerate(left):
            if u in self.matches:
                v = self.matches[u][0]
                if v in target:
                    weight = len(self.old[u]["tokens"]) + len(self.new[v]["tokens"])
                    edges.append((i, target[v], max(1, weight)))
        self.budget.charge("lis", len(edges) ** 2, "weighted LIS")
        stable = weighted_lis(edges, len(left), len(right))
        return {left[i] for i, j, _ in edges if (i, j) not in stable}

    def record(self, u, v, parent, moved):
        old, new = self.old.get(u), self.new.get(v)
        kind = (old or new)["node_type"]
        warnings = []
        for node in (old, new):
            if node and node["body_warning"] and node["body_warning"] not in warnings:
                warnings.append(node["body_warning"])
        candidates = self.alternatives(u, v)
        runner_up = candidates[0]["score"] if candidates else 0
        score = gap = confidence = 0.0
        stage = "UNMATCHED"
        ambiguous = bool(candidates)
        if old and new:
            _, score, stage = self.matches[u]
            gap = max(0., score - runner_up)
            confidence = 1.0 if stage == ANCHOR else (score + gap) / 2
            ambiguous = stage != ANCHOR and (score < self.config["tau_high"] or gap < self.config["delta_margin"])
            modified = old["tokens"] != new["tokens"]
            if not old["key"] and not new["key"] and old["number_label"] != new["number_label"]:
                ambiguous = True
            if moved or parent == "CHANGED":
                category = "MOVED_AND_MODIFIED" if modified else "MOVED"
            elif modified:
                category = "MODIFIED"
            else:
                category = "UNCHANGED" if old["number_label"] == new["number_label"] else "RENUMBERED"
            if bool(old["title"]) != bool(new["title"]):
                warnings.append("TITLE_ONE_SIDED")
            if old["section_context"] != new["section_context"]:
                warnings.append("SECTION_CONTEXT_CHANGED")
            if bool(old["children"]) != bool(new["children"]):
                warnings.append("CLAUSE_STRUCTURE_MISMATCH")
        else:
            category = "DELETED" if old else "ADDED"
        repeated = (old and self.left_counts[old["key"]] > 1) or (new and self.right_counts[new["key"]] > 1)
        if ambiguous or (kind == "CLAUSE" and repeated):
            warnings.append("AMBIGUOUS_CLAUSE_ALIGNMENT")
        if parent == "UNKNOWN":
            warnings.append("PARENT_ALIGNMENT_UNKNOWN")
        if parent == "CHANGED":
            warnings.append("CROSS_ARTICLE_CLAUSE_MOVE")
        return {"old_node_id": u, "new_node_id": v, "node_type": kind, "alignment_stage": stage,
                "category": category, "parent_status": parent,
                "parent_changed": {"SAME": False, "CHANGED": True}.get(parent),
                "similarity_score": score, "alignment_confidence": confidence, "second_best_gap": gap,
                "alternative_candidates": candidates, "warnings": warnings, "needs_review": bool(warnings)}


def align_documents(old_nodes, new_nodes, config=None, budget=None, *, observe=None):
    config = {**ALIGNMENT_CONFIG, **(config or {})}
    validate_config(config)
    budget = budget or AlignmentBudget()
    old, new = prepare(old_nodes, "old"), prepare(new_nodes, "new")
    levels = {}
    for kind in ("ARTICLE", "CLAUSE", *BLOCK_TYPES):
        levels[kind] = MatchingLevel({u: n for u, n in old.items() if n["node_type"] == kind},
                                     {v: n for v, n in new.items() if n["node_type"] == kind}, config, budget, observe)
    articles, clauses = levels["ARTICLE"], levels["CLAUSE"]
    articles.assign(articles.old_keys, articles.new_keys, ARTICLE)
    parents = {u: v for u, (v, _, _) in articles.matches.items()}
    paired_parents = set(parents.values())
    for u, v in parents.items():
        clauses.assign(old[u]["children"], new[v]["children"], LOCAL)
    clauses.recover()
    for kind in BLOCK_TYPES:
        level = levels[kind]
        level.assign(level.old_keys, level.new_keys, BLOCK)
    moved = articles.moved(articles.old_keys, articles.new_keys)
    for u, v in parents.items():
        moved.update(clauses.moved(old[u]["children"], new[v]["children"]))
    result, used = [], set()
    for u, node in old.items():
        level = levels[node["node_type"]]
        match = level.matches.get(u)
        v = match[0] if match else None
        parent = None
        if v is not None:
            used.add(v)
            if level is clauses:
                a, b = node["parent_id"], new[v]["parent_id"]
                if parents.get(a) == b:
                    parent = "SAME"
                elif a in parents or b in paired_parents:
                    parent = "CHANGED"
                else:
                    parent = "UNKNOWN"
        result.append(level.record(u, v, parent, u in moved))
    for v, node in new.items():
        if v not in used:
            result.append(levels[node["node_type"]].record(None, v, None, False))
    return result

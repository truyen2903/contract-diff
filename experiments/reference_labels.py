"""Small independent exhaustive references. No production algorithm imports."""

from fractions import Fraction
from itertools import combinations


def assignment_objective(matrix, pairs, alpha=0):
    a = max(len(matrix) - 1, 1)
    b = max(len(matrix[0]) - 1, 1) if matrix else 1
    primary = sum((Fraction(matrix[i][j]) - Fraction(alpha) for i, j in pairs), Fraction())
    return primary, sum(a*b - abs(i*b - j*a) for i, j in pairs)


def assignment_oracle(matrix, threshold=.4, alpha=0):
    if len(matrix) > 8 or any(len(row) > 8 for row in matrix):
        raise ValueError("exhaustive reference limited to 8 by 8")
    best, objective = [], (0, 0)

    def visit(row, used, pairs):
        nonlocal best, objective
        if row == len(matrix):
            value = assignment_objective(matrix, pairs, alpha)
            if value > objective:
                best, objective = list(pairs), value
            return
        visit(row + 1, used, pairs)  # deletion dummy, unused columns are insertion dummies
        for j, score in enumerate(matrix[row]):
            if j not in used and score is not None and score >= threshold:
                visit(row + 1, used | {j}, pairs + [(row, j)])

    visit(0, set(), [])
    return best


def lis_oracle(edges, m, n):
    if len(edges) > 12:
        raise ValueError("exhaustive LIS limited to 12")
    best, objective = (), (0, 0, 0, ())
    for size in range(1, len(edges) + 1):
        for seq in combinations(sorted(edges), size):
            sources = [i for i, _, _ in seq]
            targets = [j for _, j, _ in seq]
            if sources != sorted(set(sources)) or targets != sorted(set(targets)):
                continue
            displacement = sum(abs(Fraction(i, m) - Fraction(j, n)) for i, j, _ in seq)
            value = (sum(w for _, _, w in seq), size, -displacement,
                     tuple(-i for i, _, _ in seq))
            if value > objective:
                best, objective = seq, value
    return {(i, j) for i, j, _ in best}


def category_oracle(old, new, parent, stable, node_type="CLAUSE"):
    if old is None:
        return "ADDED"
    if new is None:
        return "DELETED"
    changed = old["body"].split() != new["body"].split()
    if parent == "CHANGED" or (node_type in ("ARTICLE", "CLAUSE") and parent != "UNKNOWN" and not stable):
        return ("MOVED", "MOVED_AND_MODIFIED")[changed]
    if changed:
        return "MODIFIED"
    return ("UNCHANGED", "RENUMBERED")[old["label"] != new["label"]]


def reference_stable(edges, m, n):
    if len(edges) <= 12:
        return lis_oracle(edges, m, n)
    ordered = sorted(edges)
    values, predecessors = [], []
    for index, (i, j, weight) in enumerate(ordered):
        value = (weight, 1, -abs(Fraction(i, m) - Fraction(j, n)), (-i,))
        predecessor = None
        for previous in range(index):
            previous_i, previous_j, _ = ordered[previous]
            if previous_i >= i or previous_j >= j:
                continue
            candidate = (values[previous][0] + weight, values[previous][1] + 1,
                         values[previous][2] - abs(Fraction(i, m) - Fraction(j, n)),
                         values[previous][3] + (-i,))
            if candidate > value:
                value, predecessor = candidate, previous
        values.append(value)
        predecessors.append(predecessor)
    objective = (0, 0, 0, ())
    last = None
    for index, value in enumerate(values):
        if value > objective:
            objective, last = value, index
    kept = []
    while last is not None:
        kept.append(ordered[last][:2])
        last = predecessors[last]
    return set(reversed(kept))


def reference_moves(case):
    old, new = ({n["node_id"]: n for n in case[side + "_nodes"]} for side in ("old", "new"))
    pairs = dict(case["edges"])
    if len(pairs) != len(case["edges"]) or len(set(pairs.values())) != len(pairs):
        raise ValueError("gold alignment must be one-to-one")
    parents = {u: v for u, v in pairs.items() if old[u]["node_type"] == "ARTICLE"}
    paired_new = set(parents.values())
    moved = set()
    groups = [(list(n for n in old if old[n]["node_type"] == "ARTICLE"),
               list(n for n in new if new[n]["node_type"] == "ARTICLE"))]
    for a, b in parents.items():
        groups.append((old[a]["children"], new[b]["children"]))
    for u, v in pairs.items():
        if old[u]["node_type"] != new[v]["node_type"]:
            raise ValueError("gold edge crosses node types")
        if old[u]["node_type"] == "CLAUSE":
            a, b = old[u]["parent_id"], new[v]["parent_id"]
            if parents.get(a) != b and (a in parents or b in paired_new):
                moved.add((u, v))
    for left, right in groups:
        index = {v: j for j, v in enumerate(right)}
        edges = []
        for i, u in enumerate(left):
            v = pairs.get(u)
            if v in index:
                weight = len(old[u]["body"].split()) + len(new[v]["body"].split())
                edges.append((i, index[v], max(weight, 1)))
        kept = reference_stable(edges, len(left), len(right))
        moved.update((left[i], right[j]) for i, j, _ in edges if (i, j) not in kept)
    return moved

"""Maximum-weight partial bipartite assignment with exact dyadic objectives."""

import math
from collections import defaultdict

from app.engines.alignment_budget import AlignmentBudget, AlignmentBudgetError


def components(edges):
    columns = defaultdict(list)
    rows = defaultdict(list)
    for i, j in edges:
        columns[j].append(i)
        rows[i].append(j)
    seen = set()
    for root in rows:
        if root in seen:
            continue
        left, right = set(), set()
        pending = [root]
        seen.add(root)
        while pending:
            i = pending.pop()
            left.add(i)
            for j in rows[i]:
                if j in right:
                    continue
                right.add(j)
                for neighbour in columns[j]:
                    if neighbour not in seen:
                        pending.append(neighbour)
                        seen.add(neighbour)
        yield sorted(left), sorted(right)


def hungarian(weights):
    # Shortest augmenting paths. Index zero is the unmatched sentinel column.
    n = len(weights)
    u, v = [0] * (n + 1), [0] * (n + 1)
    owner, predecessor = [0] * (n + 1), [0] * (n + 1)
    for row in range(1, n + 1):
        owner[0] = row
        distance = [None] * (n + 1)
        visited = [False] * (n + 1)
        column = 0
        while True:
            visited[column] = True
            i = owner[column]
            delta = None
            for j in range(1, n + 1):
                if visited[j]:
                    continue
                cost = -weights[i - 1][j - 1] - u[i] - v[j]
                if distance[j] is None or cost < distance[j]:
                    distance[j] = cost
                    predecessor[j] = column
                if delta is None or distance[j] < delta:
                    delta, next_column = distance[j], j
            for j in range(n + 1):
                if visited[j]:
                    u[owner[j]] += delta
                    v[j] -= delta
                else:
                    distance[j] -= delta
            column = next_column
            if owner[column] == 0:
                break
        while column:
            previous = predecessor[column]
            owner[column] = owner[previous]
            column = previous
    return [(owner[j] - 1, j - 1) for j in range(1, n + 1)]


def uncross(pairs, weights, left, right, old_keys, new_keys):
    groups = defaultdict(list)
    for i, j in sorted(pairs):
        if old_keys[left[i]] == new_keys[right[j]]:
            groups[old_keys[left[i]]].append((i, j))
    result = dict(pairs)
    for group in groups.values():
        # Swapping adjacent reversed targets strictly reduces inversions.
        for end in range(len(group) - 1, 0, -1):
            changed = False
            for index in range(end):
                i, k = group[index][0], group[index + 1][0]
                j, l = result[i], result[k]
                if j > l and weights[i][l] and weights[k][j]:
                    if weights[i][l] + weights[k][j] == weights[i][j] + weights[k][l]:
                        result[i], result[k] = l, j
                        changed = True
            if not changed:
                break
    return list(result.items())


def solve_assignment(matrix, threshold=.4, alpha=0, *, old_pos=None, new_pos=None,
                     scope=None, old_keys=None, new_keys=None, budget=None, stage="assignment"):
    if not 0 <= alpha < threshold <= 1:
        raise ValueError("expected 0 <= alpha < threshold <= 1")
    m = len(matrix)
    n = len(matrix[0]) if m else len(new_pos or new_keys or ())
    if any(len(row) != n for row in matrix):
        raise ValueError("ragged matrix")
    old_pos = range(m) if old_pos is None else old_pos
    new_pos = range(n) if new_pos is None else new_pos
    m0, n0 = scope or (m, n)
    for positions, size, bound in ((old_pos, m, m0), (new_pos, n, n0)):
        if (type(bound) is not int or bound < size or len(positions) != size or len(set(positions)) != size
                or any(type(pos) is not int or not 0 <= pos < bound for pos in positions)):
            raise ValueError("invalid original assignment positions")
    if (old_keys is None) != (new_keys is None) or old_keys is not None and (len(old_keys) != m or len(new_keys) != n):
        raise ValueError("invalid assignment keys")
    a, b = max(m0 - 1, 1), max(n0 - 1, 1)
    alpha_num, alpha_den = alpha.as_integer_ratio()
    scale = alpha_den
    ratios = {}
    for i, row in enumerate(matrix):
        for j, value in enumerate(row):
            if value is None:
                continue
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("invalid similarity")
            if value >= threshold:
                ratios[i, j] = numerator, denominator = value.as_integer_ratio()
                scale = max(scale, denominator)
    budget = budget or AlignmentBudget()
    islands = list(components(ratios))
    for left, right in islands:
        size = max(len(left), len(right))
        if size > budget.max_dimension:
            raise AlignmentBudgetError(f"{stage}: component dimension {size} > {budget.max_dimension}")
        budget.charge("cubic", size ** 3, stage)
    penalty = alpha_num * (scale // alpha_den)
    result = []
    for left, right in islands:
        size = max(len(left), len(right))
        base = size * a * b + 1
        weights = [[0] * size for _ in range(size)]
        for r, i in enumerate(left):
            for s, j in enumerate(right):
                if (i, j) in ratios:
                    num, den = ratios[i, j]
                    tie = a * b - abs(old_pos[i] * b - new_pos[j] * a)
                    weights[r][s] = (num * (scale // den) - penalty) * base + tie
        pairs = [(r, s) for r, s in hungarian(weights) if weights[r][s]]
        if old_keys is not None and new_keys is not None:
            pairs = uncross(pairs, weights, left, right, old_keys, new_keys)
        result.extend((left[r], right[s]) for r, s in pairs)
    return sorted(result)

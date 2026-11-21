"""One set of cumulative counters per comparison, including recovery and margins."""

from dataclasses import dataclass, field

from app.core import config


class AlignmentBudgetError(ValueError):
    code = "ALIGNMENT_BUDGET_EXCEEDED"
    side = None


class StructureTooLargeError(ValueError):
    code = "STRUCTURE_TOO_LARGE"


class AlignmentResultTooLargeError(ValueError):
    code = "RESULT_TOO_LARGE"
    side = None


@dataclass
class AlignmentBudget:
    max_pairs: int = config.MAX_ALIGNMENT_PAIRS
    max_score_work: int = config.MAX_SCORE_WORK
    max_dimension: int = config.MAX_ASSIGNMENT_DIMENSION
    max_cubic: int = config.MAX_ASSIGNMENT_CUBIC
    max_lis: int = config.MAX_LIS_WORK
    max_diff_total: int = config.MAX_DIFF_TOTAL_WORK
    max_b3_entities: int = config.MAX_B3_ENTITIES_TOTAL
    max_b3_pair_candidates: int = config.MAX_B3_PAIR_CANDIDATES
    max_b3_pair_candidates_total: int = config.MAX_B3_PAIR_CANDIDATES_TOTAL
    max_b3_token_ops: int = config.MAX_B3_TOKEN_OPERATIONS
    used: dict = field(default_factory=dict, init=False)

    def charge(self, resource, work, stage):
        total = self.used.get(resource, 0) + work
        limit = getattr(self, "max_" + resource)
        if total > limit:
            raise AlignmentBudgetError(f"{stage}: {resource} {total} > {limit}")
        self.used[resource] = total

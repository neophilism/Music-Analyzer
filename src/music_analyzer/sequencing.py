"""Merge ascending valence groups using deterministic dynamic programming."""

from dataclasses import asdict, dataclass

from music_analyzer.domain import Track
from music_analyzer.scoring import finite


@dataclass
class Album:
    order: list[str]
    positive: list[str]
    negative: list[str]
    warnings: list[str]
    cost: float

    def to_dict(self):
        return asdict(self)


def transition_cost(previous, following, same_bucket, mode="balanced"):
    alternation = 10000. if mode == "alternating" else 8. if mode == "balanced" else 0.
    drop_weight = 10000. if mode == "global" else 12.
    return (alternation if same_bucket else 0.) + drop_weight * max(0, previous - following) / 100 + abs(previous - following) / 100


def order_warnings(order, scores):
    warnings = []
    repeats = sum(scores[a]["bucket"] == scores[b]["bucket"] for a, b in zip(order, order[1:], strict=False))
    drops = sum(scores[a]["intensity"] > scores[b]["intensity"] + 1e-7 for a, b in zip(order, order[1:], strict=False))
    if repeats:
        warnings.append(f"{repeats} neighboring pair(s) share a valence; counts, pins, or finale prevent full alternation.")
    if drops:
        warnings.append(f"{drops} local intensity drop(s) remain while each generated valence group rises.")
    return warnings


def build_album(tracks: list[Track], scores: dict[str, dict], mode="balanced", pins=None, require_review=True) -> Album:
    if mode not in {"balanced", "alternating", "global"}:
        raise ValueError("Unknown sequencing mode.")
    included = [t for t in tracks if not t.excluded]
    unresolved = [t.original_name for t in included if t.status != "complete" or not scores.get(t.id, {}).get("bucket")
                  or not finite(scores.get(t.id, {}).get("intensity"))
                  or (require_review and scores[t.id].get("needs_review"))]
    if unresolved:
        raise ValueError(f"Review, analyze, or exclude {len(unresolved)} track(s) first: " + ", ".join(unresolved[:5]))
    positive = sorted([t.id for t in included if scores[t.id]["bucket"] == "positive"], key=lambda tid: (scores[tid]["intensity"], tid))
    negative = sorted([t.id for t in included if scores[t.id]["bucket"] == "negative"], key=lambda tid: (scores[tid]["intensity"], tid))
    total = len(included)
    pins = dict(pins or {})
    if any(tid not in positive + negative or not isinstance(position, int) or not 1 <= position <= total for tid, position in pins.items()):
        raise ValueError("Pins must refer to included tracks and valid one-based album positions.")
    if len(set(pins.values())) != len(pins):
        raise ValueError("Two tracks cannot be pinned to the same position.")
    if not total:
        return Album([], [], [], ["No included tracks"], 0.)
    reserved = {position: tid for tid, position in pins.items()}
    p_count, n_count = len(positive), len(negative)
    both = bool(p_count and n_count)

    def solve(enforce_start, enforce_final):
        initial = (0, 0, "")
        costs, parents = {initial: 0.}, {}
        for i in range(p_count + 1):
            for j in range(n_count + 1):
                for last in ("", "positive", "negative"):
                    state = (i, j, last)
                    if state not in costs:
                        continue
                    position = i + j + 1
                    previous_id = positive[i - 1] if last == "positive" else negative[j - 1] if last == "negative" else None
                    for bucket, group, index, destination in (("positive", positive, i, (i + 1, j, "positive")),
                                                              ("negative", negative, j, (i, j + 1, "negative"))):
                        if index >= len(group):
                            continue
                        tid = group[index]
                        if (tid in pins and pins[tid] != position) or (position in reserved and reserved[position] != tid):
                            continue
                        if enforce_start and both:
                            if position == 1 and bucket != "positive":
                                continue
                            if position == 2 and bucket != "negative":
                                continue
                        if enforce_final and both:
                            if position == total and bucket != "positive":
                                continue
                            if position == total - 1 and bucket != "negative":
                                continue
                        extra = transition_cost(scores[previous_id]["intensity"], scores[tid]["intensity"], last == bucket, mode) if previous_id else 0.
                        candidate_cost = costs[state] + extra
                        if candidate_cost < costs.get(destination, float("inf")) - 1e-12:
                            costs[destination] = candidate_cost
                            parents[destination] = (state, tid)
        finals = [(costs[state], state) for state in ((p_count, n_count, "positive"), (p_count, n_count, "negative")) if state in costs]
        if not finals:
            return None
        cost, state = min(finals)
        order = []
        while state != initial:
            state, tid = parents[state]
            order.append(tid)
        return list(reversed(order)), cost

    warnings = []
    endpoints = mode == "balanced"
    result = solve(endpoints, endpoints)
    if result is None and endpoints:
        warnings.append("Opening positive/negative pair relaxed to preserve the strongest negative then positive finale or pins.")
        result = solve(False, True)
    if result is None and endpoints:
        warnings.append("Finale endpoints relaxed because the explicit pins take precedence.")
        result = solve(False, False)
    if result is None:
        raise ValueError("These pins conflict with ascending intensity within a valence group. Move or remove the conflicting pins.")
    order, cost = result
    if not both:
        warnings.append("Only one valence group is present; tracks rise by intensity without alternation.")
    warnings.extend(order_warnings(order, scores))
    return Album(order, positive, negative, warnings, cost)


def validate_manual_order(order: list[str], tracks: list[Track], scores: dict[str, dict], pins=None) -> list[str]:
    included = {track.id for track in tracks if not track.excluded}
    if len(order) != len(included) or set(order) != included:
        raise ValueError("A manual album must contain every included track exactly once.")
    for tid, position in (pins or {}).items():
        if order[position - 1] != tid:
            raise ValueError("The manual move conflicts with a pinned album position.")
    warnings = order_warnings(order, scores)
    for bucket in ("positive", "negative"):
        members = [tid for tid in order if scores[tid]["bucket"] == bucket]
        if any(scores[a]["intensity"] > scores[b]["intensity"] for a, b in zip(members, members[1:], strict=False)):
            warnings.append(f"Custom order overrides ascending intensity within the {bucket} folder.")
    return warnings

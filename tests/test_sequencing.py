import itertools

import pytest

from music_analyzer.domain import Track
from music_analyzer.sequencing import build_album, transition_cost


def corpus(p, n):
    tracks, scores = [], {}
    for bucket, count in (("positive", p), ("negative", n)):
        for i in range(count):
            tid = f"{bucket}{i}"
            tracks.append(Track(id=tid, path="/x.wav", original_name=tid, status="complete", reviewed=True))
            scores[tid] = {"bucket": bucket, "intensity": 10 + i * 15 + (3 if bucket == "negative" else 0), "needs_review": False}
    return tracks, scores


@pytest.mark.parametrize("p,n", list(itertools.product(range(1, 5), repeat=2)))
def test_every_track_once_groups_ascend_and_finale_preserved(p, n):
    tracks, scores = corpus(p, n)
    album = build_album(tracks, scores)
    assert len(album.order) == p + n and len(set(album.order)) == p + n
    assert album.order[-2:] == [f"negative{n - 1}", f"positive{p - 1}"]
    assert [tid for tid in album.order if tid.startswith("positive")] == album.positive
    assert [tid for tid in album.order if tid.startswith("negative")] == album.negative
    if p >= 2 and (n >= 2 or p == 2):
        assert album.order[:2] == ["positive0", "negative0"]
    assert build_album(tracks, scores).order == album.order


def test_equal_counts_exposes_required_alternation_break():
    tracks, scores = corpus(3, 3)
    album = build_album(tracks, scores)
    assert album.order[0] == "positive0" and album.order[-1] == "positive2"
    assert any("share a valence" in warning for warning in album.warnings)


def test_global_sort_and_hard_pins():
    tracks, scores = corpus(3, 3)
    assert [scores[tid]["intensity"] for tid in build_album(tracks, scores, mode="global").order] == sorted(v["intensity"] for v in scores.values())
    album = build_album(tracks, scores, pins={"negative0": 1})
    assert album.order[0] == "negative0"
    with pytest.raises(ValueError, match="conflict"):
        build_album(tracks, scores, pins={"positive2": 1})


def test_dp_is_minimum_cost_over_feasible_small_merges():
    tracks, scores = corpus(3, 2)
    album = build_album(tracks, scores)
    costs = []
    for p_positions in itertools.combinations(range(5), 3):
        p_index = n_index = 0
        order = []
        for position in range(5):
            if position in p_positions:
                order.append(f"positive{p_index}")
                p_index += 1
            else:
                order.append(f"negative{n_index}")
                n_index += 1
        if order[:2] != ["positive0", "negative0"] or order[-2:] != ["negative1", "positive2"]:
            continue
        costs.append(sum(transition_cost(scores[a]["intensity"], scores[b]["intensity"], scores[a]["bucket"] == scores[b]["bucket"])
                         for a, b in zip(order, order[1:], strict=False)))
    assert album.cost == pytest.approx(min(costs))

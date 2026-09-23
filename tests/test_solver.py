"""求解器单元测试: 固定用例 + 与暴力枚举对照的随机化测试。"""
from __future__ import annotations

import itertools
import random
import time

from app.solver import solve_seating


def brute_force(guests, forbidden, scores, fixed):
    """暴力枚举参考实现, 与求解器语义保持一致 (n=2 时邻边只计一次)。"""
    n = len(guests)
    ids = sorted(guests)
    edges = [(i, (i + 1) % n) for i in range(n)]
    if n == 2:
        edges = [(0, 1)]
    best_total = None
    best_seq = None
    for perm in itertools.permutations(ids):
        if any(perm[seat - 1] != g for seat, g in fixed.items()):
            continue
        if any(
            (min(perm[i], perm[j]), max(perm[i], perm[j])) in forbidden
            for i, j in edges
        ):
            continue
        total = sum(
            scores.get((min(perm[i], perm[j]), max(perm[i], perm[j])), 0)
            for i, j in edges
        )
        if (
            best_total is None
            or total > best_total
            or (total == best_total and list(perm) < best_seq)
        ):
            best_total = total
            best_seq = list(perm)
    return best_total, best_seq


def solve(guests, forbidden=(), scores=None, fixed=None):
    return solve_seating(
        guest_ids=list(guests),
        forbidden_pairs=[tuple(p) for p in forbidden],
        pair_scores={
            (min(a, b), max(a, b)): v for (a, b), v in (scores or {}).items()
        },
        fixed_seats=dict(fixed or {}),
    )


def test_basic_maximization():
    # 4 人, 让 1-2、2-3、3-4 相邻得分高 -> 最优圈 1-2-3-4 (总分 30)
    result = solve(
        [1, 2, 3, 4],
        scores={(1, 2): 10, (2, 3): 10, (3, 4): 10},
    )
    assert result.feasible
    assert result.total_score == 30
    assert result.sequence == [1, 2, 3, 4]


def test_wraparound_edge_counted():
    # 首尾相邻边计入总分: 圈 1-2-3 的三条边都计分
    result = solve([1, 2, 3], scores={(1, 3): 7, (1, 2): 5})
    assert result.feasible
    assert result.total_score == 12  # (1,2)+(1,3) 两条边, (2,3) 为 0
    assert set(result.sequence) == {1, 2, 3}


def test_two_guests_edge_counted_once():
    result = solve([1, 2], scores={(1, 2): 5})
    assert result.feasible
    assert result.total_score == 5
    assert result.sequence == [1, 2]


def test_forbidden_pair_avoided():
    # 1 与 2 禁邻, 4 人圆桌中 1 的邻居只能是 3、4
    result = solve([1, 2, 3, 4], forbidden=[(1, 2)])
    assert result.feasible
    seq = result.sequence
    i1, i2 = seq.index(1), seq.index(2)
    assert (i1 - i2) % 4 not in (1, 3)  # 不相邻


def test_forbidden_infeasible_two_guests():
    result = solve([1, 2], forbidden=[(1, 2)])
    assert not result.feasible
    assert result.reason


def test_forbidden_infeasible_all_pairs():
    # 3 人两两禁邻 -> 不可行
    result = solve([1, 2, 3], forbidden=[(1, 2), (1, 3), (2, 3)])
    assert not result.feasible
    assert result.reason


def test_fixed_seats_respected():
    result = solve([1, 2, 3, 4], fixed={2: 4, 4: 1})
    assert result.feasible
    assert result.sequence[1] == 4
    assert result.sequence[3] == 1


def test_fixed_seats_force_forbidden_adjacency():
    # 固定座位 1、2 分别坐 1、2, 但 1-2 禁邻 -> 不可行且说明原因
    result = solve([1, 2, 3], forbidden=[(1, 2)], fixed={1: 1, 2: 2})
    assert not result.feasible
    assert "禁邻" in result.reason


def test_tie_break_lexicographic():
    # 全部 0 分 -> 取字典序最小序列
    result = solve([3, 1, 2, 4])
    assert result.feasible
    assert result.sequence == [1, 2, 3, 4]
    assert result.total_score == 0


def test_tie_break_lexicographic_with_scores():
    # (1,3)=10 使最优圈必须含 1-3 邻边; 多个最优中选字典序最小
    best_total, best_seq = brute_force(
        [1, 2, 3, 4], set(), {(1, 3): 10}, {}
    )
    result = solve([1, 2, 3, 4], scores={(1, 3): 10})
    assert result.feasible
    assert result.total_score == best_total
    assert result.sequence == best_seq


def test_negative_scores():
    result = solve([1, 2, 3], scores={(1, 2): -5, (2, 3): -1})
    assert result.feasible
    best_total, best_seq = brute_force(
        [1, 2, 3], set(), {(1, 2): -5, (2, 3): -1}, {}
    )
    assert result.total_score == best_total
    assert result.sequence == best_seq


def test_randomized_against_brute_force():
    rng = random.Random(20260923)
    for n in range(2, 8):
        for _ in range(60):
            guests = list(range(1, n + 1))
            pairs = list(itertools.combinations(guests, 2))
            scores = {
                p: rng.randint(-9, 9) for p in pairs if rng.random() < 0.5
            }
            forbidden = {
                p
                for p in pairs
                if p not in scores and rng.random() < 0.25
            }
            fixed = {}
            seats = rng.sample(range(1, n + 1), k=rng.randint(0, n // 3))
            members = rng.sample(guests, k=len(seats))
            for seat, guest in zip(seats, members):
                fixed[seat] = guest

            best_total, best_seq = brute_force(
                guests, forbidden, scores, fixed
            )
            result = solve(guests, forbidden, scores, fixed)
            if best_seq is None:
                assert not result.feasible, (n, scores, forbidden, fixed)
                assert result.reason
            else:
                assert result.feasible, (n, scores, forbidden, fixed)
                assert result.total_score == best_total, (
                    n, scores, forbidden, fixed,
                )
                assert result.sequence == best_seq, (
                    n, scores, forbidden, fixed,
                )


def test_twelve_guests_performance():
    rng = random.Random(7)
    guests = list(range(1, 13))
    scores = {
        p: rng.randint(-20, 20)
        for p in itertools.combinations(guests, 2)
        if rng.random() < 0.6
    }
    forbidden = [
        p
        for p in itertools.combinations(guests, 2)
        if p not in scores and rng.random() < 0.1
    ]
    start = time.monotonic()
    result = solve(guests, forbidden, scores, fixed={3: 12})
    elapsed = time.monotonic() - start
    assert result.feasible
    assert len(result.sequence) == 12
    assert result.sequence[2] == 12
    assert elapsed < 30  # 充裕上限, 正常应在数秒内

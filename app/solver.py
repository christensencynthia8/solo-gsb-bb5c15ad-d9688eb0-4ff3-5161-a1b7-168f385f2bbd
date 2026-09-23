"""圆桌座位优化核心求解器。

问题: n 位宾客 (2 <= n <= 12) 围坐圆桌, 座位从 1 编号。需要:
  1. 避开所有禁邻宾客对;
  2. 满足固定座位约束;
  3. 最大化整圈相邻得分之和 (座位 n 与座位 1 也相邻);
  4. 最高得分并列时, 取从 1 号位开始宾客编号序列字典序最小者。

算法: 基于子集的动态规划。
  - 状态 dp[mask][last]: 1 号位固定为某位宾客 first 时, 已安排 mask 中的宾客、
    最后一位 (当前末位) 为 last 的最大前缀得分;
  - 对每个可行的 1 号位宾客做一次前向 DP, 闭合末位与首位之间的边, 取全局最优;
  - 对最优首位再做一次反向 DP, 自座位 1 起按宾客编号升序贪心恢复字典序最小方案。
复杂度 O(n * 2^n * n^2), n <= 12 时秒级完成。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

NEG_INF = float("-inf")


@dataclass
class SolveResult:
    """求解结果。不可行时 feasible=False 且 reason 说明原因。"""

    feasible: bool
    sequence: Optional[list[int]] = None  # 1 号位起的宾客编号序列
    total_score: Optional[float] = None   # 整圈相邻总分
    reason: Optional[str] = None


def solve_seating(
    guest_ids: list[int],
    forbidden_pairs: list[tuple[int, int]],
    pair_scores: dict[tuple[int, int], float],
    fixed_seats: dict[int, int],
) -> SolveResult:
    """计算最优圆桌座位安排。

    参数:
        guest_ids:      宾客编号列表 (调用方保证 2~12 个且互不重复);
        forbidden_pairs: 禁邻宾客对列表 (无序);
        pair_scores:    宾客对 -> 相邻得分 (无序键), 未配置的对按 0 分计;
        fixed_seats:    1 基座位号 -> 宾客编号。
    """
    n = len(guest_ids)
    ordered_ids = sorted(guest_ids)
    # 内部用 0..n-1 索引, 索引顺序即宾客编号升序, 便于字典序比较
    idx_of = {g: i for i, g in enumerate(ordered_ids)}

    # 对称的得分矩阵与禁邻矩阵
    score = [[0.0] * n for _ in range(n)]
    for (a, b), value in pair_scores.items():
        ia, ib = idx_of[a], idx_of[b]
        score[ia][ib] = value
        score[ib][ia] = value

    forbidden = [[False] * n for _ in range(n)]
    for a, b in forbidden_pairs:
        ia, ib = idx_of[a], idx_of[b]
        forbidden[ia][ib] = True
        forbidden[ib][ia] = True

    # fixed[s]: 0 基座位 s 上被固定的宾客索引, -1 表示未固定
    fixed = [-1] * n
    for seat, guest in fixed_seats.items():
        fixed[seat - 1] = idx_of[guest]

    full_mask = (1 << n) - 1
    # n == 2 时首尾边与唯一一条邻边是同一对宾客, 只计一次, 故不再单独闭合
    close_edge = n >= 3

    # 每个座位可安排的宾客 (固定座位约束), 每个 (last, seat) 可接的宾客
    candidates = [[[] for _ in range(n)] for _ in range(n)]
    for last in range(n):
        for seat in range(n):
            candidates[last][seat] = [
                g
                for g in range(n)
                if fixed[seat] in (-1, g) and not forbidden[last][g]
            ]
    first_choices = [g for g in range(n) if fixed[0] in (-1, g)]

    # 无任何固定座位时, 圆桌旋转不影响可行性与得分, 字典序最小的最优方案
    # 必然以编号最小的宾客开头 (取最优圈旋转即可), 只需枚举一个首位
    if not fixed_seats:
        first_choices = [0]

    all_masks = range(1 << n)
    bit_count = [mask.bit_count() for mask in range(1 << n)]

    def run_forward(first: int):
        """首位固定为 first 时的前向 DP, 返回 dp 表与闭合后的最高总分。"""
        dp = [[NEG_INF] * n for _ in range(1 << n)]
        dp[1 << first][first] = 0
        for mask in all_masks:
            if not (mask >> first) & 1:
                continue
            seat = bit_count[mask]  # 下一个要填的座位 (0 基)
            if seat >= n:
                continue
            row = dp[mask]
            for last in range(n):
                base = row[last]
                if base == NEG_INF:
                    continue
                srow = score[last]
                for g in candidates[last][seat]:
                    if (mask >> g) & 1:
                        continue
                    new_mask = mask | (1 << g)
                    value = base + srow[g]
                    if value > dp[new_mask][g]:
                        dp[new_mask][g] = value

        best = NEG_INF
        final_row = dp[full_mask]
        for last in range(n):
            value = final_row[last]
            if value == NEG_INF:
                continue
            if close_edge:
                if forbidden[last][first]:
                    continue
                value += score[last][first]
            if value > best:
                best = value
        return dp, best

    best_total = NEG_INF
    best_first = -1
    best_dp = None
    for first in first_choices:
        dp, total = run_forward(first)
        if total > best_total:
            best_total = total
            best_first = first
            best_dp = dp

    if best_first < 0:
        return SolveResult(
            feasible=False,
            reason=_infeasible_reason(
                ordered_ids, forbidden, fixed, fixed_seats
            ),
        )

    # 反向 DP: 从状态 (mask, last) 出发到补全整圈 (含闭合边) 能再获得的最高分
    rest = [[NEG_INF] * n for _ in range(1 << n)]
    for last in range(n):
        if not close_edge:
            rest[full_mask][last] = 0
        elif not forbidden[last][best_first]:
            rest[full_mask][last] = score[last][best_first]

    for mask in range(full_mask - 1, -1, -1):
        if not (mask >> best_first) & 1:
            continue
        seat = bit_count[mask]
        for last in range(n):
            if not ((mask >> last) & 1):
                continue
            best = NEG_INF
            srow = score[last]
            for g in candidates[last][seat]:
                if (mask >> g) & 1:
                    continue
                tail = rest[mask | (1 << g)][g]
                if tail == NEG_INF:
                    continue
                cand = srow[g] + tail
                if cand > best:
                    best = cand
            rest[mask][last] = best

    # 贪心恢复: 每个座位按宾客编号 (索引) 升序尝试, 选择仍能达到最优总分的首位候选
    eps = 1e-9 * max(1.0, abs(best_total))
    seq = [best_first]
    mask = 1 << best_first
    last = best_first
    prefix = 0
    for seat in range(1, n):
        chosen = -1
        srow = score[last]
        for g in candidates[last][seat]:
            if (mask >> g) & 1:
                continue
            projected = prefix + srow[g] + rest[mask | (1 << g)][g]
            if abs(projected - best_total) <= eps:
                chosen = g
                break
        if chosen < 0:
            # 理论上不可达: best_total 已由前向 DP 证实可行
            return SolveResult(feasible=False, reason="内部错误: 方案恢复失败")
        seq.append(chosen)
        mask |= 1 << chosen
        prefix += score[last][chosen]
        last = chosen

    total = best_total
    if isinstance(total, float) and total.is_integer():
        total = int(total)
    return SolveResult(
        feasible=True,
        sequence=[ordered_ids[i] for i in seq],
        total_score=total,
    )


def _infeasible_reason(
    ordered_ids: list[int],
    forbidden: list[list[bool]],
    fixed: list[int],
    fixed_seats: dict[int, int],
) -> str:
    """对不可行原因给出尽量具体的说明。输入合法时不可行只可能由禁邻约束导致。"""
    n = len(ordered_ids)

    # 情况 1: 两个固定座位本身相邻, 却固定了一对禁邻
    checked = set()
    for s in range(n):
        t = (s + 1) % n
        key = (min(s, t), max(s, t))
        if key in checked:
            continue
        checked.add(key)
        a, b = fixed[s], fixed[t]
        if a >= 0 and b >= 0 and forbidden[a][b]:
            return (
                f"无可行排列: 座位 {s + 1} 的宾客 {ordered_ids[a]} 与座位 "
                f"{t + 1} 的宾客 {ordered_ids[b]} 被固定为相邻, 但二者属于禁邻宾客对。"
            )

    # 情况 2: 某位宾客与其余所有人均为禁邻, 无人可与其相邻
    for g in range(n):
        if n >= 2 and all(forbidden[g][h] for h in range(n) if h != g):
            return (
                f"无可行排列: 宾客 {ordered_ids[g]} 与其余全部宾客均为禁邻, "
                f"无法安排在任何座位。"
            )

    # 情况 3: 一般性无解 (禁邻组合 + 固定座位共同导致)
    if fixed_seats:
        fixed_desc = "、".join(
            f"座位 {seat} 固定宾客 {guest}"
            for seat, guest in sorted(fixed_seats.items())
        )
        return (
            "无可行排列: 在禁邻宾客对约束下, 无法同时满足全部固定座位要求 "
            f"({fixed_desc}), 请调整禁邻组合或固定座位。"
        )
    return "无可行排列: 禁邻宾客对约束下不存在任何满足条件的围坐排列。"

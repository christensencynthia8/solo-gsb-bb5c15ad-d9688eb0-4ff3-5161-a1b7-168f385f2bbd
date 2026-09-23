"""圆桌座位优化 API。

启动 (本地):
    pip install -r requirements.txt
    uvicorn app.main:app --host 0.0.0.0 --port 8000

容器:
    docker compose up --build
"""
from __future__ import annotations

import math
from typing import Annotated

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .solver import solve_seating

GUEST_MIN = 2
GUEST_MAX = 12


class PairScore(BaseModel):
    """一对宾客相邻时的得分。未配置的宾客对按 0 分计。"""

    guest_a: int = Field(..., description="宾客 A 编号", ge=1)
    guest_b: int = Field(..., description="宾客 B 编号", ge=1)
    score: int | float = Field(..., description="A 与 B 相邻时的得分")

    @model_validator(mode="after")
    def _check(self) -> "PairScore":
        if self.guest_a == self.guest_b:
            raise ValueError("guest_a 与 guest_b 不能相同")
        if not math.isfinite(self.score):
            raise ValueError("score 必须为有限数值")
        return self


class FixedSeat(BaseModel):
    """将某位宾客固定安排到指定座位 (座位从 1 编号)。"""

    seat: int = Field(..., description="座位号, 从 1 开始", ge=1)
    guest: int = Field(..., description="宾客编号", ge=1)


class SeatingRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "guests": [1, 2, 3, 4],
                "forbidden_pairs": [[1, 3]],
                "pair_scores": [
                    {"guest_a": 1, "guest_b": 2, "score": 5},
                    {"guest_a": 2, "guest_b": 3, "score": -2},
                ],
                "fixed_seats": [{"seat": 1, "guest": 1}],
            }
        }
    )

    guests: list[int] = Field(
        ...,
        description=(
            f"宾客编号列表, 须为 {GUEST_MIN}~{GUEST_MAX} 个互不重复的正整数; "
            "每人一席"
        ),
    )
    forbidden_pairs: list[Annotated[list[int], Field(min_length=2, max_length=2)]] = (
        Field(default_factory=list, description="禁止相邻的宾客对列表")
    )
    pair_scores: list[PairScore] = Field(
        default_factory=list, description="宾客对相邻得分列表, 未配置按 0 分计"
    )
    fixed_seats: list[FixedSeat] = Field(
        default_factory=list, description="固定座位安排列表"
    )

    @field_validator("guests")
    @classmethod
    def _validate_guests(cls, guests: list[int]) -> list[int]:
        if not (GUEST_MIN <= len(guests) <= GUEST_MAX):
            raise ValueError(
                f"宾客人数须在 {GUEST_MIN}~{GUEST_MAX} 之间, 当前为 {len(guests)}"
            )
        if len(set(guests)) != len(guests):
            raise ValueError("宾客编号不得重复")
        if any(g < 1 for g in guests):
            raise ValueError("宾客编号须为正整数")
        return guests

    @field_validator("forbidden_pairs")
    @classmethod
    def _validate_forbidden(cls, pairs: list[list[int]]) -> list[list[int]]:
        for pair in pairs:
            a, b = pair
            if a == b:
                raise ValueError("禁邻宾客对的两位宾客不能相同")
            if a < 1 or b < 1:
                raise ValueError("宾客编号须为正整数")
        return pairs

    @model_validator(mode="after")
    def _check_references_and_conflicts(self) -> "SeatingRequest":
        guest_set = set(self.guests)

        def _require_guest(guest: int, where: str) -> None:
            if guest not in guest_set:
                raise ValueError(f"{where} 引用了宾客列表中不存在的宾客 {guest}")

        for a, b in self.forbidden_pairs:
            _require_guest(a, "禁邻宾客对")
            _require_guest(b, "禁邻宾客对")

        forbidden = {tuple(sorted(pair)) for pair in self.forbidden_pairs}
        for item in self.pair_scores:
            _require_guest(item.guest_a, "pair_scores")
            _require_guest(item.guest_b, "pair_scores")
            if (min(item.guest_a, item.guest_b), max(item.guest_a, item.guest_b)) in forbidden:
                raise ValueError(
                    f"宾客 {item.guest_a} 与 {item.guest_b} 同时出现在禁邻对和"
                    "相邻得分中, 二者矛盾"
                )

        seat_to_guest: dict[int, int] = {}
        guest_to_seat: dict[int, int] = {}
        for item in self.fixed_seats:
            if not (1 <= item.seat <= len(self.guests)):
                raise ValueError(
                    f"座位号 {item.seat} 超出范围, 有效座位为 1~{len(self.guests)}"
                )
            _require_guest(item.guest, "fixed_seats")
            if item.seat in seat_to_guest and seat_to_guest[item.seat] != item.guest:
                raise ValueError(
                    f"座位 {item.seat} 被同时固定给宾客 "
                    f"{seat_to_guest[item.seat]} 和 {item.guest}"
                )
            if item.guest in guest_to_seat and guest_to_seat[item.guest] != item.seat:
                raise ValueError(
                    f"宾客 {item.guest} 被同时固定到座位 "
                    f"{guest_to_seat[item.guest]} 和 {item.seat}"
                )
            seat_to_guest[item.seat] = item.guest
            guest_to_seat[item.guest] = item.seat
        return self


class SeatingResponse(BaseModel):
    feasible: bool = Field(..., description="是否存在满足全部约束的排列")
    arrangement: list[int] | None = Field(
        None, description="1 号位起的宾客编号序列 (不可行为 null)"
    )
    total_score: int | float | None = Field(
        None, description="整圈相邻得分之和 (含首尾相邻), 不可行为 null"
    )
    edge_scores: list[dict] | None = Field(
        None, description="逐边相邻情况: 座位、宾客及该边得分"
    )
    reason: str | None = Field(None, description="不可行原因 (可行时为 null)")


app = FastAPI(
    title="圆桌座位优化 API",
    description=(
        "给定 2~12 位宾客、禁邻宾客对、宾客对相邻得分及固定座位, "
        "避开禁邻并满足固定座位, 最大化整圈 (含首尾相邻) 总得分; "
        "同分时取从 1 号位起宾客编号序列字典序最小者。"
    ),
    version="1.0.0",
)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["系统"])
def health() -> dict:
    """健康检查。"""
    return {"status": "ok"}


@app.post(
    "/api/v1/seating/optimize",
    response_model=SeatingResponse,
    tags=["座位优化"],
    summary="计算最优圆桌座位排列",
)
def optimize_seating(req: SeatingRequest) -> SeatingResponse:
    # 同一对宾客若给了多个得分, 以最后一条为准
    pair_scores: dict[tuple[int, int], float] = {}
    for item in req.pair_scores:
        key = (min(item.guest_a, item.guest_b), max(item.guest_a, item.guest_b))
        pair_scores[key] = item.score

    fixed_seats = {item.seat: item.guest for item in req.fixed_seats}

    result = solve_seating(
        guest_ids=req.guests,
        forbidden_pairs=[tuple(pair) for pair in req.forbidden_pairs],
        pair_scores=pair_scores,
        fixed_seats=fixed_seats,
    )

    if not result.feasible:
        return SeatingResponse(feasible=False, reason=result.reason)

    # 逐边明细, 首尾相邻显式作为最后一条边
    n = len(result.sequence)
    edge_scores: list[dict] = []
    for pos in range(n):
        a = result.sequence[pos]
        b = result.sequence[(pos + 1) % n]
        edge_scores.append(
            {
                "from_seat": pos + 1,
                "to_seat": (pos + 1) % n + 1,
                "guest_a": a,
                "guest_b": b,
                "score": pair_scores.get((min(a, b), max(a, b)), 0.0),
            }
        )
    return SeatingResponse(
        feasible=True,
        arrangement=result.sequence,
        total_score=result.total_score,
        edge_scores=edge_scores,
    )


if __name__ == "__main__":
    import os

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8000")),
        log_level=os.getenv("APP_LOG_LEVEL", "info"),
    )

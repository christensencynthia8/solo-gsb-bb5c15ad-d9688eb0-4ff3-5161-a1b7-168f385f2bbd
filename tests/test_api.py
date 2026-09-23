"""API 接口测试。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_optimize_success():
    resp = client.post(
        "/api/v1/seating/optimize",
        json={
            "guests": [1, 2, 3, 4],
            "forbidden_pairs": [[1, 3]],
            "pair_scores": [
                {"guest_a": 1, "guest_b": 2, "score": 5},
                {"guest_a": 2, "guest_b": 4, "score": 3},
            ],
            "fixed_seats": [{"seat": 1, "guest": 1}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["feasible"] is True
    assert body["arrangement"][0] == 1
    assert sorted(body["arrangement"]) == [1, 2, 3, 4]
    # 1 与 3 禁邻: 校验整圈 (含首尾) 不相邻
    seq = body["arrangement"]
    n = len(seq)
    for i in range(n):
        pair = {seq[i], seq[(i + 1) % n]}
        assert pair != {1, 3}
    assert body["total_score"] == sum(e["score"] for e in body["edge_scores"])
    assert body["reason"] is None


def test_optimize_defaults_zero_score():
    resp = client.post("/api/v1/seating/optimize", json={"guests": [2, 1, 3]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["feasible"] is True
    assert body["total_score"] == 0
    assert body["arrangement"] == [1, 2, 3]  # 同分取字典序最小


def test_optimize_infeasible_returns_reason():
    resp = client.post(
        "/api/v1/seating/optimize",
        json={"guests": [1, 2], "forbidden_pairs": [[1, 2]]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["feasible"] is False
    assert body["reason"]
    assert body["arrangement"] is None
    assert body["total_score"] is None


def test_guest_count_bounds():
    assert client.post(
        "/api/v1/seating/optimize", json={"guests": [1]}
    ).status_code == 422
    assert client.post(
        "/api/v1/seating/optimize", json={"guests": list(range(1, 14))}
    ).status_code == 422


def test_duplicate_guests_rejected():
    resp = client.post(
        "/api/v1/seating/optimize", json={"guests": [1, 2, 2]}
    )
    assert resp.status_code == 422


def test_unknown_guest_reference_rejected():
    resp = client.post(
        "/api/v1/seating/optimize",
        json={"guests": [1, 2, 3], "forbidden_pairs": [[1, 9]]},
    )
    assert resp.status_code == 422


def test_seat_out_of_range_rejected():
    resp = client.post(
        "/api/v1/seating/optimize",
        json={"guests": [1, 2, 3], "fixed_seats": [{"seat": 4, "guest": 1}]},
    )
    assert resp.status_code == 422


def test_conflicting_fixed_seats_rejected():
    resp = client.post(
        "/api/v1/seating/optimize",
        json={
            "guests": [1, 2, 3],
            "fixed_seats": [{"seat": 1, "guest": 1}, {"seat": 2, "guest": 1}],
        },
    )
    assert resp.status_code == 422


def test_forbidden_and_scored_pair_conflict_rejected():
    resp = client.post(
        "/api/v1/seating/optimize",
        json={
            "guests": [1, 2, 3],
            "forbidden_pairs": [[1, 2]],
            "pair_scores": [{"guest_a": 2, "guest_b": 1, "score": 5}],
        },
    )
    assert resp.status_code == 422

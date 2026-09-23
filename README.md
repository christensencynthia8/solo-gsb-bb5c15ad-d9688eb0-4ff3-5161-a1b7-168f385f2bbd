# 圆桌座位优化 API

基于 Python + FastAPI 的圆桌座位优化服务。给定 2～12 位宾客（每人一席）、禁邻宾客对、
宾客对相邻得分及固定座位，服务在避开禁邻并满足固定座位的前提下，最大化整圈
（含首尾相邻）相邻得分；同分时取从 1 号位起宾客编号序列字典序最小的排列；
无可行排列时返回具体原因。

## 快速开始（单条启动命令）

```bash
docker compose up --build
```

依赖安装（镜像构建时 `pip install -r requirements.txt`）与应用初始化启动均已纳入
该命令，无需任何额外步骤。

启动后：

| 内容 | 地址 |
| --- | --- |
| API 地址 | http://localhost:8000 |
| 交互式文档 (Swagger UI) | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/health |
| 排列计算接口 | `POST http://localhost:8000/api/v1/seating/optimize` |

停止服务：`docker compose down`。

## 配置项

均为环境变量，均可在 `docker compose up` 前导出，或写入 compose 的 `environment`：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_PORT` | `8000` | 宿主机映射端口（容器内固定监听 8000） |
| `APP_LOG_LEVEL` | `info` | uvicorn 日志级别 |

示例：`APP_PORT=9000 docker compose up --build`，此时 API 地址为 http://localhost:9000。

## API 说明

### `POST /api/v1/seating/optimize`

请求体：

```json
{
  "guests": [1, 2, 3, 4, 5],
  "forbidden_pairs": [[1, 2]],
  "pair_scores": [
    {"guest_a": 1, "guest_b": 3, "score": 8},
    {"guest_a": 3, "guest_b": 5, "score": 6}
  ],
  "fixed_seats": [{"seat": 1, "guest": 1}]
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `guests` | `int[]` | 是 | 宾客编号列表，2～12 个互不重复的正整数，每人一席 |
| `forbidden_pairs` | `[int, int][]` | 否 | 禁止相邻的宾客对（无序） |
| `pair_scores` | `object[]` | 否 | 宾客对相邻得分；**未配置的宾客对按 0 分计**；同一对重复配置时以最后一条为准 |
| `fixed_seats` | `object[]` | 否 | 固定座位，`seat` 从 **1** 开始编号，`guest` 为宾客编号 |

成功响应（HTTP 200）：

```json
{
  "feasible": true,
  "arrangement": [1, 3, 5, 2, 4],
  "total_score": 18,
  "edge_scores": [
    {"from_seat": 1, "to_seat": 2, "guest_a": 1, "guest_b": 3, "score": 8},
    {"from_seat": 2, "to_seat": 3, "guest_a": 3, "guest_b": 5, "score": 6},
    {"from_seat": 3, "to_seat": 4, "guest_a": 5, "guest_b": 2, "score": 0.0},
    {"from_seat": 4, "to_seat": 5, "guest_a": 2, "guest_b": 4, "score": 4},
    {"from_seat": 5, "to_seat": 1, "guest_a": 4, "guest_b": 1, "score": 0.0}
  ],
  "reason": null
}
```

- `arrangement`：从 1 号位起的宾客编号序列；
- `total_score`：整圈相邻得分之和，**含首尾相邻边**（`edge_scores` 最后一条即座位 n 与座位 1 的邻边）；
- 最高得分存在多个排列时，返回 `arrangement` 字典序最小者。

无可行排列时仍返回 HTTP 200，`feasible=false` 并给出原因：

```json
{
  "feasible": false,
  "arrangement": null,
  "total_score": null,
  "edge_scores": null,
  "reason": "无可行排列: 座位 1 的宾客 1 与座位 2 的宾客 2 被固定为相邻, 但二者属于禁邻宾客对。"
}
```

输入不合法（人数越界、编号重复、引用不存在的宾客、座位号超出 `1~n`、固定座位冲突、
同一对宾客既禁邻又配置得分等）返回 HTTP 422 及具体错误信息。

调用示例：

```bash
curl -X POST http://localhost:8000/api/v1/seating/optimize \
  -H "Content-Type: application/json" \
  -d '{"guests": [1, 2, 3, 4], "forbidden_pairs": [[1, 3]], "fixed_seats": [{"seat": 1, "guest": 1}]}'
```

## 规则说明

- 座位从 1 编号，1 号位与 n 号位相邻（圆桌首尾相邻），该边计入总分；
- 仅 2 位宾客时，两人互为唯一邻居，该相邻关系只计一次得分；
- 禁邻约束为硬约束，优先级最高；固定座位必须满足；
- 同分时按从 1 号位起的宾客编号序列取字典序最小者（编号按数值比较）。

## 本地开发（不用 Docker）

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000   # 或 python -m app.main
pytest                                      # 运行测试
```

## 项目结构

```
app/
  main.py      # FastAPI 应用、请求校验、接口定义
  solver.py    # 座位优化求解器（子集 DP + 字典序恢复）
tests/
  test_api.py     # 接口测试
  test_solver.py  # 求解器测试（含与暴力枚举对照的随机化测试）
Dockerfile
docker-compose.yml
requirements.txt
```

## 实现说明

求解器采用子集动态规划：枚举 1 号位宾客，状态 `dp[已安排宾客集合][末位宾客]` 记录
最大前缀得分，闭合末位与首位的邻边后取全局最优；再对最优首位做反向 DP，并从 1 号位
起按宾客编号升序贪心恢复出字典序最小的最优排列。复杂度 `O(n·2ⁿ·n²)`，12 位宾客
最坏情况秒级内完成（实测 < 1 秒）。

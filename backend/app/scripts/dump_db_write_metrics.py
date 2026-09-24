"""文件功能：只读导出运行中 Backend 的 SQLite 写路径打点快照，供基线采集与诊断使用。"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

METRICS_PATH = "/metrics/db-write"


def fetch_snapshot(base_url: str, *, timeout: float) -> dict[str, object]:
    """从目标 Backend 拉取写路径打点快照。

    打点计数保存在目标进程的模块内存中，本脚本必须走 HTTP 读取，
    进程内直接 import app.db.metrics 只会得到全 0 的空快照。
    """

    url = base_url.rstrip("/") + METRICS_PATH
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.load(response)


def main(argv: list[str] | None = None) -> int:
    """打印目标 Backend 的写路径指标 JSON；不修改任何运行态。"""

    parser = argparse.ArgumentParser(description="导出数据库写路径打点快照")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Backend 基地址；网关未转发 /metrics/db-write，需直连 Backend 端口。",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="请求超时秒数。")
    args = parser.parse_args(argv)

    try:
        payload = fetch_snapshot(args.base_url, timeout=args.timeout)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"读取写路径打点失败：{exc}", file=sys.stderr)
        return 1

    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

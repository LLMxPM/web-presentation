"""文件功能：在隔离镜像内通过真实 Renderer 控制 API 完成截图、下载与消费确认。"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from render_contracts.constants import PROTOCOL_VERSION
from render_contracts.schema import ExecutionRequest, SnapshotRef, ViewportSpec
from render_contracts.tokens import (
    AdmissionTicket,
    PreviewAccess,
    issue_worker_credential,
)
from wp_renderer.config import get_renderer_settings

ARTIFACT = "image-smoke-artifact"
DIGEST = "image-smoke-input"
WIDTH, HEIGHT = 320, 240


class PreviewFixture(BaseHTTPRequestHandler):
    """提供无外部依赖的固定双色页面与正式 render-ready 协议，仅服务本次镜像探针。"""

    def do_GET(self) -> None:
        """由生产 Chromium 访问页面；固定内容可用于检查下载的截图确实来自该页面。"""
        content = (
            f"<body style='margin:0;background:rgb(12,34,56)'><div style='height:120px;background:rgb(210,80,30)'></div>"
            f"<script>window.__RENDER_READY__={{protocol:'render-ready.v1',artifactId:'{ARTIFACT}',"
            f"inputDigest:'{DIGEST}',mounted:true,fonts:{{ready:true}},visualAssets:{{ready:true}}}}</script>"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *_args: object) -> None:
        """不把预览请求头、票据或访问路径写入探针日志。"""


def run_probe(output: Path) -> None:
    """只操作当前隔离容器的本地服务，不覆盖执行器、不注入浏览器启动参数。"""
    settings = get_renderer_settings()
    token = issue_worker_credential(
        worker_id=f"backend:{settings.render_worker_id}",
        secret=settings.credential_secret,
    )
    origin = f"http://127.0.0.1:{settings.render_port}"

    def request(path: str, method: str = "GET", payload: dict | None = None) -> bytes:
        """调用控制 API，凭证仅在内存与请求头中传递。"""
        data = json.dumps(payload).encode() if payload is not None else None
        req = Request(
            origin + path,
            data=data,
            method=method,
            headers={
                "x-render-service-token": token,
                "Content-Type": "application/json",
            },
        )
        with urlopen(req, timeout=10) as response:
            return response.read(32 * 1024 * 1024 + 1)

    prefix = "/internal/render/v1"
    capabilities = json.loads(request(prefix + "/capabilities"))
    if capabilities["slot_state"] != "idle":
        raise RuntimeError("镜像探针要求独占空闲 Renderer")
    server = ThreadingHTTPServer(("127.0.0.1", 0), PreviewFixture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    attempt = "image-smoke-attempt"
    execution_path = f"{prefix}/executions/{attempt}"
    try:
        now = datetime.now(UTC)
        deadline = now + timedelta(seconds=45)
        execution = ExecutionRequest(
            contract_version=PROTOCOL_VERSION,
            operation="page.capture",
            request_id="image-smoke-request",
            attempt_id=attempt,
            request_digest=DIGEST,
            workspace_id=1,
            trace_id="image-smoke",
            snapshot_ref=SnapshotRef(artifact_id=ARTIFACT, input_digest=DIGEST),
            input_digest=DIGEST,
            render_profile_digest=capabilities["render_profile_digest"],
            viewport=ViewportSpec(width=WIDTH, height=HEIGHT),
            operation_options={},
            deadline_at=deadline.isoformat(),
            remaining_budget_ms=45_000,
            admission_ticket=AdmissionTicket.issue(
                secret=settings.credential_secret,
                request_digest=DIGEST,
                workspace_id=1,
                worker_id=capabilities["worker_id"],
                worker_epoch=capabilities["worker_epoch"],
                slot_generation=capabilities["slot_generation"] + 1,
                accept_before=now + timedelta(seconds=10),
                stop_by=deadline,
                attempt_id=attempt,
            ),
            preview_access=PreviewAccess(
                navigation_base_url=f"http://127.0.0.1:{server.server_port}/preview",
                preview_token="fixture-only",
                artifact_id=ARTIFACT,
                expires_at=deadline.isoformat(),
                runtime_protocol_version="render-ready.v1",
            ),
        )
        request(prefix + "/executions", "POST", execution.to_dict())
        timeout = time.monotonic() + 55
        while time.monotonic() < timeout:
            receipt = json.loads(request(execution_path))
            if receipt["status"] in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("Renderer 截图探针超时")
        if receipt["status"] != "succeeded" or not receipt["cleaned_at"]:
            raise RuntimeError(f"Renderer 执行或清理失败：{receipt.get('error')}")
        png = request(execution_path + "/artifacts/page.png")
        descriptor = receipt["result_descriptor"]["artifacts"][0]
        if (
            len(png) != descriptor["byte_length"]
            or hashlib.sha256(png).hexdigest() != descriptor["sha256"]
        ):
            raise RuntimeError("截图下载与结果描述符不一致")
        output.mkdir(parents=True, exist_ok=True)
        (output / "page.png").write_bytes(png)
        (output / "receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        request(execution_path + "/result-consumption", "PUT", {})
        if json.loads(request(prefix + "/capabilities"))["slot_state"] != "idle":
            raise RuntimeError("截图完成后槽位未释放")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    run_probe(Path("/tmp/wp-image-evidence"))

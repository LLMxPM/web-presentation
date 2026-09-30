"""文件功能：仅在专属 Docker 演练中延迟真实导航或 PNG 响应，不伪造 Renderer 回执和产物。"""

from __future__ import annotations

import hashlib
import json
import threading
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class FaultGate:
    """每次只阻塞一个场景，状态仅含计数、attempt ID 和 PNG 摘要。"""

    def __init__(self) -> None:
        """初始化直通模式；旧等待线程持有自己的释放事件，不污染下一轮。"""
        self.lock = threading.Lock()
        self.release = threading.Event()
        self.release.set()
        self.mode = "pass"
        self.target = None
        self.records: list[dict] = []

    def configure(self, mode: str) -> None:
        """切换 gate 前释放旧线程，未知模式拒绝，所有等待最多 90 秒。"""
        if mode not in {"pass", "navigation", "artifact"}:
            raise ValueError("未知故障模式")
        with self.lock:
            self.release.set()
            self.release = threading.Event()
            if mode == "pass":
                self.release.set()
            self.mode, self.target, self.records = mode, None, []

    def wait(self, kind: str, record: dict) -> None:
        """仅延迟第一 attempt 的真实 PNG；导航 gate 阻塞本场景所有导航。"""
        with self.lock:
            if self.mode != kind:
                return
            if kind == "artifact":
                if self.target is None:
                    self.target = record["attempt_id"]
                if self.target != record["attempt_id"]:
                    return
            self.records.append(record)
            release = self.release
        if not release.wait(90):
            raise TimeoutError("故障 gate 等待超过 90 秒")

    def state(self) -> dict:
        """输出脱敏状态，不保留导航 URL、凭证或执行请求正文。"""
        with self.lock:
            return {"mode": self.mode, "released": self.release.is_set(), "records": list(self.records)}


GATE = FaultGate()


class Handler(BaseHTTPRequestHandler):
    """固定转发到本测试网络的 Runtime 或 Renderer，禁止任意代理目标。"""

    def do_GET(self) -> None:
        """读取 gate 状态或转发 GET；控制入口只在预览代理端口生效。"""
        if self.server.server_port == 8091 and self.path == "/_drill/status":
            self.respond(200, json.dumps(GATE.state()).encode(), "application/json")
        else:
            self.forward()

    def do_POST(self) -> None:
        """配置/释放 gate，其余 POST 沿真实接管接口转发。"""
        if self.server.server_port == 8091 and self.path in {"/_drill/configure", "/_drill/release"}:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.path.endswith("configure"):
                try:
                    GATE.configure(payload["mode"])
                except (KeyError, ValueError):
                    self.respond(400, b'{}', "application/json")
                    return
            else:
                GATE.release.set()
            self.respond(200, json.dumps(GATE.state()).encode(), "application/json")
        else:
            self.forward()

    def do_PUT(self) -> None:
        """取消和消费确认直接转发，不改变业务语义。"""
        self.forward()

    def forward(self) -> None:
        """转发有界真实响应；导航在请求前阻塞，PNG 在下载完成后阻塞。"""
        port = self.server.server_port
        path = urlsplit(self.path).path
        target = {8091: ("preview_a", 7373), 8092: ("renderer_1", 7400), 8093: ("renderer_2", 7400)}[port]
        if port == 8091 and path != "/runtime/__preview":
            self.respond(404, b'{}', "application/json")
            return
        connection = HTTPConnection(*target, timeout=30)
        try:
            if port == 8091:
                GATE.wait("navigation", {"kind": "navigation"})
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            headers = {key: value for key, value in self.headers.items() if key.lower() not in {"host", "connection"}}
            headers["Host"] = "gateway" if port == 8091 else target[0]
            connection.request(self.command, self.path, body=body or None, headers=headers)
            response = connection.getresponse()
            content = response.read(33 * 1024 * 1024)
            if len(content) >= 33 * 1024 * 1024:
                raise ValueError("代理响应超过演练上限")
            if "/artifacts/" in path and response.status == 200:
                if not content.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("产物 gate 必须返回真实 PNG")
                GATE.wait("artifact", {"kind": "artifact", "attempt_id": path.split("/")[5],
                                       "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
            self.respond(response.status, content, response.getheader("Content-Type", "application/octet-stream"))
        except (OSError, TimeoutError, ValueError):
            self.respond(502, b'{"code":"DRILL_UPSTREAM_UNAVAILABLE"}', "application/json")
        finally:
            connection.close()

    def respond(self, status: int, content: bytes, content_type: str) -> None:
        """显式写入响应长度；取消已关闭连接时安静结束，避免日志带出 URL。"""
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *_args: object) -> None:
        """不记录包含票据的路径和 HTTP 身份头。"""


def main() -> None:
    """在隔离服务内启动三个固定目标代理，不提供通用外网代理。"""
    for port in (8092, 8093):
        server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8091), Handler).serve_forever()


if __name__ == "__main__":
    main()

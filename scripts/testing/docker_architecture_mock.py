"""文件功能：提供可释放的本地 Chat Completions 流，验证真实 AI 执行器长时间无模型事件。"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RELEASE = threading.Event()
ARRIVALS: list[float] = []


class Handler(BaseHTTPRequestHandler):
    """不记录消息、工具参数或 Authorization，只暴露到达数与释放控制。"""

    def do_GET(self) -> None:
        """读取状态或释放所有等待流；仅位于随机隔离网络。"""
        if self.path == "/release":
            RELEASE.set()
        if self.path == "/reset":
            RELEASE.clear()
            ARRIVALS.clear()
        body = json.dumps({"arrivals": len(ARRIVALS), "released": RELEASE.is_set()}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        """在真正模型请求到达后等待控制指令，随后返回标准 SSE 文本及停止帧。"""
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        ARRIVALS.append(time.monotonic())
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.flush()
        if not RELEASE.wait(90):
            return
        base = {"id": "local-drill", "object": "chat.completion.chunk", "created": int(time.time()), "model": payload["model"]}
        for delta, reason in (({"role": "assistant", "content": "本地隔离模型响应完成。"}, None), ({}, "stop")):
            chunk = {**base, "choices": [{"index": 0, "delta": delta, "finish_reason": reason}]}
            try:
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
        self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, *_args: object) -> None:
        """避免日志泄露输入消息与访问凭证。"""


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()

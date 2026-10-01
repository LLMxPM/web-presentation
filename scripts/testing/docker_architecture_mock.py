"""文件功能：提供可释放的本地 Chat Completions 流，验证真实 AI 执行器长时间无模型事件。"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RELEASE = threading.Event()
ARRIVALS: list[float] = []
SCENARIO: dict = {}
SCENARIO_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    """不记录消息、工具参数或 Authorization，只暴露到达数与释放控制。"""

    def do_GET(self) -> None:
        """读取状态或释放所有等待流；仅位于随机隔离网络。"""
        if self.path == "/release":
            RELEASE.set()
        if self.path == "/reset":
            RELEASE.clear()
            ARRIVALS.clear()
        body = json.dumps({"arrivals": len(ARRIVALS), "released": RELEASE.is_set(),
                           "scenario_requests": SCENARIO.get("requests", 0)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        """在真正模型请求到达后等待控制指令，随后返回标准 SSE 文本及停止帧。"""
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/_drill/scenario":
            with SCENARIO_LOCK:
                SCENARIO.clear()
                SCENARIO.update(payload, requests=0)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"configured"}')
            return
        ARRIVALS.append(time.monotonic())
        with SCENARIO_LOCK:
            scenario = dict(SCENARIO)
            if scenario:
                SCENARIO["requests"] += 1
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.flush()
        if not scenario and not RELEASE.wait(90):
            return
        base = {"id": "local-drill", "object": "chat.completion.chunk", "created": int(time.time()), "model": payload["model"]}
        if scenario and scenario["requests"] == 0:
            delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": "m05-page-create", "type": "function",
                     "function": {"name": "create_entity", "arguments": json.dumps(scenario["arguments"], ensure_ascii=False)}}]}
            frames = ((delta, None), ({}, "tool_calls"))
        else:
            frames = (({"role": "assistant", "content": "本地隔离模型响应完成。"}, None), ({}, "stop"))
        for delta, reason in frames:
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

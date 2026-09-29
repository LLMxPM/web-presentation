"""文件功能：完整部署探针的有界 HTTP 客户端，只在内存保存测试账号 Cookie。"""

from __future__ import annotations

import json
import time
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener


class ProbeClient:
    """绑定一个 Gateway；跨源产物下载使用独立、无凭证的客户端。"""

    def __init__(self, base_url: str) -> None:
        """只接受无用户信息和查询参数的 HTTP(S) Gateway 根地址。"""
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "base-url 必须是 HTTP(S) Gateway 地址，不能包含凭证或查询参数"
            )
        self.base_url = base_url.rstrip("/") + "/"
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def fetch(
        self, path: str, *, payload: dict | None = None, limit: int = 4 * 1024 * 1024
    ) -> bytes:
        """读取有界响应；业务请求必须同源，错误日志不打印带令牌的 URL 或响应正文。"""
        url = urljoin(self.base_url, path)
        same_origin = urlsplit(url)[:2] == urlsplit(self.base_url)[:2]
        if urlsplit(url).scheme not in {"http", "https"} or (
            payload is not None and not same_origin
        ):
            raise ValueError("业务写请求必须留在指定 Gateway")
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(url, data=data, headers={"Content-Type": "application/json"})
        opener = self.opener if same_origin else build_opener()
        try:
            with opener.open(request, timeout=30) as response:
                body = response.read(limit + 1)
        except HTTPError as error:
            raise RuntimeError(f"部署探针 HTTP 请求失败，状态码 {error.code}") from None
        if len(body) > limit:
            raise ValueError("产物超过探针读取上限")
        return body

    def json(self, path: str, payload: dict | None = None) -> dict:
        """读取 API JSON，登录响应只用于内存会话，不写到证据文件。"""
        return json.loads(self.fetch(path, payload=payload))

    def wait_job(self, path: str, timeout: int) -> dict:
        """轮询持久化任务；只接受 succeeded，跳过、取消与超时均不作为成功。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.json(path)
            if job["status"] == "succeeded":
                return job
            if job["status"] not in {"pending", "running"}:
                raise RuntimeError(f"任务 {job['id']} 未成功：{job['status']}")
            time.sleep(1)
        raise TimeoutError(
            "部署探针任务等待超时；任务可能仍在运行，请按记录的任务 ID 排查"
        )

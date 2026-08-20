"""文件功能：封装 External API v1 的 HTTP 客户端，处理认证、空间隔离、幂等头与任务轮询。"""

from __future__ import annotations

import time
import uuid
from typing import Any, Mapping

import httpx

from wp.config import ProfileConfig


class ApiClientError(Exception):
    """API 调用异常。"""

    def __init__(self, message: str, status_code: int = 500, code: str = "ERROR", details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details


class ApiClient:
    """External API v1 交互客户端。"""

    def __init__(self, profile: ProfileConfig, workspace_id: int | None = None) -> None:
        self.endpoint = profile.endpoint.rstrip("/")
        self.token = profile.token
        self.workspace_id = workspace_id or profile.default_workspace_id
        self.client = httpx.Client(base_url=self.endpoint, timeout=30.0)

    def _get_headers(
        self,
        *,
        idempotent: bool = False,
        custom_idempotency_key: str | None = None,
        override_workspace_id: int | None = None,
    ) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "web-presentation-cli/0.1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        ws_id = override_workspace_id or self.workspace_id
        if ws_id is not None:
            headers["X-Workspace-ID"] = str(ws_id)

        if idempotent:
            headers["Idempotency-Key"] = custom_idempotency_key or uuid.uuid4().hex

        return headers

    def _handle_response(self, response: httpx.Response) -> Any:
        if response.is_success:
            if response.status_code == 204 or not response.content:
                return {}
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                return response.json()
            return response.text

        # 错误解析
        err_msg = f"HTTP {response.status_code} 请求失败"
        code = "HTTP_ERROR"
        details = None
        try:
            err_json = response.json()
            err_msg = err_json.get("message") or err_msg
            code = err_json.get("code") or code
            details = err_json.get("data")
        except Exception:
            err_msg = response.text or err_msg

        raise ApiClientError(err_msg, status_code=response.status_code, code=code, details=details)

    def get(self, path: str, params: Mapping[str, Any] | None = None, workspace_id: int | None = None) -> Any:
        url = f"/api/v1{path}"
        headers = self._get_headers(override_workspace_id=workspace_id)
        resp = self.client.get(url, params=params, headers=headers)
        return self._handle_response(resp)

    def post(
        self,
        path: str,
        json_data: Any | None = None,
        idempotent: bool = True,
        idempotency_key: str | None = None,
        workspace_id: int | None = None,
    ) -> Any:
        url = f"/api/v1{path}"
        headers = self._get_headers(
            idempotent=idempotent,
            custom_idempotency_key=idempotency_key,
            override_workspace_id=workspace_id,
        )
        resp = self.client.post(url, json=json_data, headers=headers)
        return self._handle_response(resp)

    def patch(
        self,
        path: str,
        json_data: Any | None = None,
        idempotent: bool = True,
        idempotency_key: str | None = None,
        workspace_id: int | None = None,
    ) -> Any:
        url = f"/api/v1{path}"
        headers = self._get_headers(
            idempotent=idempotent,
            custom_idempotency_key=idempotency_key,
            override_workspace_id=workspace_id,
        )
        resp = self.client.patch(url, json=json_data, headers=headers)
        return self._handle_response(resp)

    def put(
        self,
        path: str,
        json_data: Any | None = None,
        idempotent: bool = True,
        idempotency_key: str | None = None,
        workspace_id: int | None = None,
    ) -> Any:
        url = f"/api/v1{path}"
        headers = self._get_headers(
            idempotent=idempotent,
            custom_idempotency_key=idempotency_key,
            override_workspace_id=workspace_id,
        )
        resp = self.client.put(url, json=json_data, headers=headers)
        return self._handle_response(resp)

    def delete(
        self,
        path: str,
        idempotent: bool = True,
        idempotency_key: str | None = None,
        workspace_id: int | None = None,
    ) -> Any:
        url = f"/api/v1{path}"
        headers = self._get_headers(
            idempotent=idempotent,
            custom_idempotency_key=idempotency_key,
            override_workspace_id=workspace_id,
        )
        resp = self.client.delete(url, headers=headers)
        return self._handle_response(resp)

    def upload(
        self,
        path: str,
        files: dict[str, Any],
        data: dict[str, Any] | None = None,
        idempotent: bool = True,
        idempotency_key: str | None = None,
        workspace_id: int | None = None,
    ) -> Any:
        url = f"/api/v1{path}"
        headers = self._get_headers(
            idempotent=idempotent,
            custom_idempotency_key=idempotency_key,
            override_workspace_id=workspace_id,
        )
        resp = self.client.post(url, data=data, files=files, headers=headers)
        return self._handle_response(resp)

    def poll_mutation_job(
        self,
        job_id: str,
        timeout_seconds: float = 60.0,
        interval: float = 1.0,
    ) -> dict[str, Any]:
        """轮询异步变更任务直到进入终态。"""

        start = time.perf_counter()
        while time.perf_counter() - start < timeout_seconds:
            job = self.get(f"/jobs/mutations/{job_id}")
            status = job.get("status")
            if status in {"succeeded", "failed", "canceled"}:
                return job
            time.sleep(interval)

        raise ApiClientError(f"等待 Mutation 任务超时 ({timeout_seconds}s)", code="TIMEOUT")

    def poll_build_job(
        self,
        job_id: int,
        timeout_seconds: float = 180.0,
        interval: float = 2.0,
    ) -> dict[str, Any]:
        """轮询构建任务直到进入终态。"""

        start = time.perf_counter()
        while time.perf_counter() - start < timeout_seconds:
            job = self.get(f"/builds/{job_id}")
            status = job.get("status")
            if status in {"succeeded", "failed"}:
                return job
            time.sleep(interval)

        raise ApiClientError(f"等待 Build 任务超时 ({timeout_seconds}s)", code="TIMEOUT")

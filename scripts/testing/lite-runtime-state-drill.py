"""文件功能：在 2C4G 限制下驱动 Lite 镜像完成运行态内存基线与重启/断连演练。

覆盖：小/中/大预览、带二进制资源的模板预览、诊断删除、构建运行态、重复刷新、
清扫延迟与容器 RSS；重启后旧临时预览失效、新预览可用、SQLite 数据保留；
真实 Redis 模式下短暂断连与恢复不留下部分 artifact。

脚本只管理自己创建的容器、网络与临时数据目录，不触碰部署环境资源。
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from datetime import UTC, datetime
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "Admin123456"
REPORT_ROOT = REPO_ROOT / "test-results" / "lite-runtime-state"
BACKEND_PROBE_PORT = 8000


def docker(*args: str, check: bool = True, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    """调用 Docker 并返回文本结果；超时与失败都直接抛出，避免演练静默失真。"""

    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=timeout)


class LiteContainer:
    """管理一个 Lite 容器实例：启动、重启、进程探针与聚合指标。"""

    def __init__(
        self,
        image: str,
        *,
        name: str,
        host_port: int,
        data_dir: Path,
        cpus: str | None = None,
        memory: str | None = None,
        network: str | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self.image = image
        self.name = name
        self.host_port = host_port
        self.data_dir = data_dir
        self.cpus = cpus
        self.memory = memory
        self.network = network
        self.extra_env = extra_env or {}

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.host_port}"

    def start(self) -> None:
        """启动容器；数据目录用于验证重启后的持久数据。"""

        self.data_dir.mkdir(parents=True, exist_ok=True)
        options = [
            "run",
            "--detach",
            "--name",
            self.name,
            "-p",
            f"{self.host_port}:80",
            "-v",
            f"{self.data_dir}:/app/backend/data",
            "-e",
            "DEFAULT_ADMIN_USERNAME=" + DEFAULT_ADMIN_USERNAME,
            "-e",
            "DEFAULT_ADMIN_PASSWORD=" + DEFAULT_ADMIN_PASSWORD,
            "-e",
            "AI_ENABLED=false",
            "-e",
            "ACCESS_LOG_ENABLED=false",
        ]
        if self.cpus:
            options += ["--cpus", self.cpus]
        if self.memory:
            options += ["--memory", self.memory]
        if self.network:
            options += ["--network", self.network]
        else:
            options += ["--network", "bridge", "--add-host", "backend:127.0.0.1", "--add-host", "runtime:127.0.0.1"]
        for key, value in self.extra_env.items():
            options += ["-e", f"{key}={value}"]
        docker(*options, self.image)
        self.wait_ready()

    def restart(self) -> None:
        """重启容器并等待就绪，用于验证重启后的运行态与持久数据语义。"""

        docker("restart", self.name)
        self.wait_ready()

    def stop(self) -> None:
        docker("rm", "--force", self.name, check=False)

    def wait_ready(self, timeout_seconds: int = 240) -> None:
        """等待网关与 Backend 同时就绪。"""

        deadline = time.monotonic() + timeout_seconds
        last_error = ""
        while time.monotonic() < deadline:
            running = docker("inspect", "--format", "{{.State.Running}}", self.name, check=False).stdout.strip()
            if running != "true":
                logs = docker("logs", "--tail", "60", self.name, check=False)
                raise RuntimeError(f"容器 {self.name} 提前退出：\n{logs.stdout}\n{logs.stderr}")
            try:
                if self.backend_probe("http://127.0.0.1/healthz"):
                    self.backend_probe(f"http://127.0.0.1:{BACKEND_PROBE_PORT}/readyz")
                    return
            except Exception as error:  # noqa: BLE001
                last_error = str(error)
            time.sleep(3)
        raise RuntimeError(f"容器 {self.name} 在 {timeout_seconds}s 内未就绪：{last_error}")

    def backend_probe(self, url: str, *, timeout: int = 5) -> Any:
        """在容器内访问 Backend 专用端点（/readyz、/metrics），不依赖网关代理。"""

        code = (
            "import json,urllib.request;"
            f"print(urllib.request.urlopen({url!r}, timeout={timeout}).read().decode())"
        )
        result = docker("exec", self.name, "python", "-c", code, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"容器内探针 {url} 失败：{result.stderr.strip()}")
        body = result.stdout.strip()
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body

    def runtime_metrics(self) -> dict[str, Any]:
        """读取运行态聚合指标（key 数、近似字节、清扫统计、容量拒绝）。"""

        return dict(self.backend_probe(f"http://127.0.0.1:{BACKEND_PROBE_PORT}/metrics/runtime-state"))

    def memory_usage(self) -> dict[str, Any]:
        """采集容器总内存与各进程 RSS，区分 Backend 与 Node 占用。"""

        stats = docker("stats", "--no-stream", "--format", "{{.MemUsage}}", self.name, check=False).stdout.strip()
        inspect = docker(
            "inspect", "--format", "{{.State.OOMKilled}} {{.RestartCount}}", self.name, check=False
        ).stdout.strip()
        oom_killed, _, restart_count = inspect.partition(" ")
        processes = self.backend_probe_processes()
        return {
            "container_mem_usage": stats,
            "oom_killed": oom_killed.strip() == "true",
            "restart_count": int(restart_count.strip() or 0),
            "processes": processes,
        }

    def backend_probe_processes(self) -> dict[str, int]:
        """读取容器内各进程 RSS（kB），按进程名归并。"""

        code = (
            "import json,os,re;"
            "out={};"
            "\nfor pid in os.listdir('/proc'):\n"
            "    if not pid.isdigit():\n"
            "        continue\n"
            "    try:\n"
            "        status=open('/proc/'+pid+'/status').read()\n"
            "    except OSError:\n"
            "        continue\n"
            "    name=re.search(r'^Name:\\s+(\\S+)', status, re.M)\n"
            "    rss=re.search(r'^VmRSS:\\s+(\\d+) kB', status, re.M)\n"
            "    if not name or not rss:\n"
            "        continue\n"
            "    out[name.group(1)]=out.get(name.group(1),0)+int(rss.group(1))\n"
            "print(json.dumps(out))"
        )
        result = docker("exec", self.name, "python", "-c", code, check=False)
        if result.returncode != 0:
            return {}
        try:
            return {str(key): int(value) for key, value in json.loads(result.stdout.strip()).items()}
        except (json.JSONDecodeError, ValueError):
            return {}


class ApiClient:
    """带 Cookie 会话的轻量 API 客户端，用于驱动真实业务接口。"""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self.failures = 0

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        raw_body: bytes | None = None,
        content_type: str | None = None,
        expect: tuple[int, ...] = (200,),
    ) -> tuple[int, Any]:
        """发送请求并返回状态码与解析后的响应；非期望状态码直接抛错。"""

        headers: dict[str, str] = {}
        data: bytes | None = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if raw_body is not None:
            data = raw_body
            headers["Content-Type"] = content_type or "application/octet-stream"
        request = urllib.request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=120) as response:
                status, payload = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, payload = error.code, error.read()
        parsed = _parse_payload(payload)
        if expect and status not in expect:
            self.failures += 1
            if expect == (200,):
                raise RuntimeError(f"{method} {path} 返回 {status}: {str(parsed)[:300]}")
        return status, parsed

    def login(self) -> None:
        self.request(
            "POST",
            "/api/auth/login",
            body={"username": DEFAULT_ADMIN_USERNAME, "password": DEFAULT_ADMIN_PASSWORD},
        )

    def request_ignoring_status(self, method: str, path: str, **kwargs: Any) -> tuple[int, Any]:
        """允许任意状态码的请求，用于断言预期失败（失效预览、限流、断连）。"""

        return self.request(method, path, expect=(), **kwargs)


def _parse_payload(payload: bytes) -> Any:
    """尝试解析 JSON，失败时返回原始文本。"""

    if not payload:
        return None
    text = payload.decode("utf-8", errors="replace")
    stripped = text.lstrip()
    if stripped.startswith(("{", "[")):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


def _multipart(field: str, filename: str, content: bytes, content_type: str) -> tuple[bytes, str]:
    """构造单文件 multipart 请求体。"""

    boundary = f"----wpdill{uuid.uuid4().hex}"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
            content,
            f"\r\n--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return body, f"multipart/form-data; boundary={boundary}"


def _build_minimal_template_package() -> bytes:
    """构造最小可解析模板包，用于覆盖带二进制资源的模板预览。"""

    exported_at = datetime.now(tz=UTC).isoformat()
    manifest = {
        "package_type": "web-presentation-project-template",
        "schema_version": 1,
        "exported_at": exported_at,
        "runtime_kit_manifest_version": "1.0.0",
        "template_path": "metadata/template.json",
        "screenshots_path": "metadata/screenshots.json",
        "project_path": "project/project.json",
        "routes_path": "project/routes.json",
        "page_count": 1,
        "component_count": 0,
        "asset_count": 0,
        "theme_count": 0,
        "font_count": 0,
        "pages": [{"source_page_code": "page_cover", "path": "pages/page_cover"}],
        "components": [],
        "assets": [],
        "themes": [],
        "fonts": [],
    }
    template = {
        "slug": f"drill-{uuid.uuid4().hex[:8]}",
        "name": "容量基线模板",
        "summary": "用于内存基线的模板包。",
        "description": "用于内存基线的模板包。",
        "author": DEFAULT_ADMIN_USERNAME,
        "page_count": 1,
        "page_width": 1920,
        "page_height": 1080,
        "aspect_ratio": "16:9",
        "runtime_kit_manifest_version": "1.0.0",
        "created_at": exported_at,
        "updated_at": exported_at,
    }
    screenshots = {
        "cover": {"path": "screenshots/cover.png", "width": 1920, "height": 1080},
        "pages": [
            {
                "source_page_code": "page_cover",
                "title": "封面",
                "path": "screenshots/pages/page_cover.png",
                "order": 1,
                "width": 1920,
                "height": 1080,
            }
        ],
    }
    project = {
        "source_project_code": "PRJ_DRILL",
        "name": "容量基线项目",
        "description": "用于内存基线的项目。",
        "page_width": 1920,
        "page_height": 1080,
        "base_font_size": "16px",
        "icon_default_stroke_width": 2,
        "show_pdf_export_button": True,
        "menu_mode": "preview",
        "theme_key": None,
        "theme_config_yaml": "themes: {}\n",
        "style_spec_markdown": "",
        "build_extra_assets_json": {"asset_names": []},
        "suggested_reference_asset_names": [],
        "suggested_components": [],
    }
    page = {
        "source_page_code": "page_cover",
        "title": "封面",
        "summary": None,
        "speaker_notes": None,
        "file_type": "vue",
    }
    routes = {
        "routes": [
            {
                "route_type": "page",
                "route": "cover",
                "order": 1,
                "hidden": False,
                "group_title": None,
                "source_page_code": "page_cover",
                "children": [],
            }
        ]
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("metadata/template.json", json.dumps(template, ensure_ascii=False))
        archive.writestr("metadata/screenshots.json", json.dumps(screenshots, ensure_ascii=False))
        archive.writestr("project/project.json", json.dumps(project, ensure_ascii=False))
        archive.writestr("project/routes.json", json.dumps(routes, ensure_ascii=False))
        archive.writestr("pages/page_cover/page.json", json.dumps(page, ensure_ascii=False))
        archive.writestr("pages/page_cover/index.vue", "<template><main>cover</main></template>")
        archive.writestr("screenshots/cover.png", _binary_blob(64 * 1024))
        archive.writestr("screenshots/pages/page_cover.png", _binary_blob(32 * 1024))
    return buffer.getvalue()


def _binary_blob(size: int) -> bytes:
    """生成不可压缩的伪二进制内容，模拟真实素材体积。"""

    header = b"\x89PNG\r\n\x1a\n"
    body = bytes((index * 37 + 11) % 256 for index in range(max(0, size - len(header))))
    return header + body


def _page_source(target_bytes: int, label: str) -> str:
    """构造接近目标体积的页面源码，覆盖小/中/大模块。"""

    filler = "\n".join(
        f"<p class=\"row-{index}\">{label} 数据行 {index} —— 用于容量基线的稳定载荷。</p>"
        for index in range(max(1, target_bytes // 96))
    )
    return f"<template>\n<main>\n{filler}\n</main>\n</template>\n"


class DrillContext:
    """一次演练/基线所需的容器、客户端与业务对象。"""

    def __init__(self, container: LiteContainer, api: ApiClient) -> None:
        self.container = container
        self.api = api
        self.workspace_id = 0
        self.project_id = 0
        self.page_ids: dict[str, int] = {}
        self.entry_route = "/"
        self.asset_id = 0
        self.template_package = b""

    def bootstrap(self, *, page_sizes: dict[str, int]) -> None:
        """创建基线所需的全部业务对象，并注册整项目预览入口路由。"""

        self.api.login()
        _, workspace = self.api.request("POST", "/api/workspaces", body={"name": "容量基线空间", "status": "active"})
        self.workspace_id = int(workspace["id"])
        _, project = self.api.request(
            "POST",
            "/api/projects",
            body={"workspace_id": self.workspace_id, "name": "容量基线项目"},
        )
        self.project_id = int(project["id"])
        routes: list[dict[str, Any]] = []
        for index, (label, size) in enumerate(page_sizes.items(), start=1):
            _, page = self.api.request(
                "POST",
                "/api/pages",
                body={
                    "project_id": self.project_id,
                    "workspace_id": self.workspace_id,
                    "title": f"基线页面-{label}",
                    "page_content": _page_source(size, label),
                    "file_type": "vue",
                },
            )
            self.page_ids[label] = int(page["id"])
            routes.append(
                {
                    "route_type": "page",
                    "route": f"page-{index}",
                    "order": index,
                    "hidden": False,
                    "page_id": int(page["id"]),
                }
            )
        self.api.request("PUT", f"/api/projects/{self.project_id}/routes", body={"routes": routes})
        self.entry_route = "/page-1"
        body, content_type = _multipart("file", "baseline.png", _binary_blob(96 * 1024), "image/png")
        _, asset = self.api.request(
            "POST",
            f"/api/workspaces/{self.workspace_id}/assets/upload",
            raw_body=body,
            content_type=content_type,
        )
        self.asset_id = int(asset["id"])
        self.template_package = _build_minimal_template_package()

    def create_project_preview(self) -> tuple[str, str]:
        """创建项目预览 artifact，返回 artifact_id 与带令牌的预览地址。"""

        _, payload = self.api.request(
            "POST",
            f"/api/projects/{self.project_id}/preview-artifacts",
            body={"entry_descriptor": {"entry_type": "route", "route": self.entry_route}},
        )
        return str(payload["artifact_id"]), str(payload["preview_url"])

    def create_asset_preview(self) -> tuple[str, str]:
        _, payload = self.api.request(
            "POST",
            f"/api/workspaces/{self.workspace_id}/assets/{self.asset_id}/preview-artifact",
        )
        return str(payload["artifact_id"]), str(payload["preview_url"])

    def create_template_preview(self) -> tuple[str, str]:
        """上传模板包并创建带二进制资源的临时预览 artifact。"""

        body, content_type = _multipart("archive", "template.zip", self.template_package, "application/zip")
        _, payload = self.api.request(
            "POST",
            f"/api/workspaces/{self.workspace_id}/template-packages/preview-artifact",
            raw_body=body,
            content_type=content_type,
        )
        return str(payload["artifact_id"]), str(payload["preview_url"])

    def create_build_job(self) -> int | None:
        """创建构建任务，覆盖任务创建后的运行态缓存写入。

        同一项目同时只允许一个活跃构建，重复创建返回 409 属于预期，不算失败。
        """

        status, payload = self.api.request_ignoring_status(
            "POST",
            f"/api/projects/{self.project_id}/build-jobs",
            body={},
        )
        if status == 409:
            return None
        if status != 200:
            raise RuntimeError(f"创建构建任务返回 {status}: {str(payload)[:200]}")
        return int(payload["id"])

    def probe_preview(self, preview_url: str) -> int:
        """访问带令牌的预览地址，返回状态码；用于确认 artifact 是否仍然可用。"""

        parts = urlsplit(preview_url)
        target = parts.path + (f"?{parts.query}" if parts.query else "")
        status, _ = self.api.request_ignoring_status("GET", target)
        return status


def _sample(container: LiteContainer, samples: list[dict[str, Any]], label: str, started: float) -> None:
    """记录一次运行态指标与内存快照。"""

    metrics = container.runtime_metrics()
    sample = {
        "label": label,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "active_keys": metrics.get("active_keys"),
        "approx_bytes": metrics.get("approx_bytes"),
        "capacity_rejections": metrics.get("capacity_rejections"),
        "sweep_count": metrics.get("sweep_count"),
        "sweep_failures": metrics.get("sweep_failures"),
        "last_sweep_seconds": metrics.get("last_sweep_seconds"),
        "memory": container.memory_usage(),
    }
    samples.append(sample)
    peak = max(item.get("approx_bytes") or 0 for item in samples)
    rss = sample["memory"]["processes"]
    backend_rss = rss.get("uvicorn") or rss.get("python") or 0
    node_rss = rss.get("node") or 0
    print(
        f"[sample] {label}: keys={sample['active_keys']} bytes={sample['approx_bytes']} "
        f"peak={peak} backend_rss={backend_rss}kB node_rss={node_rss}kB "
        f"container={sample['memory']['container_mem_usage']}"
    )


def run_baseline(args: argparse.Namespace) -> dict[str, Any]:
    """在受限资源下运行混合负载，采集运行态字节、RSS、清扫与失败记录。"""

    report: dict[str, Any] = {
        "mode": "baseline",
        "image": args.image,
        "cpus": args.cpus,
        "memory_limit": args.memory,
        "containers": 1,
        "started_at": datetime.now(tz=UTC).isoformat(),
    }
    with tempfile.TemporaryDirectory(prefix="wp-lite-baseline-") as temp_dir:
        container = LiteContainer(
            args.image,
            name=f"wp-lite-baseline-{uuid.uuid4().hex[:8]}",
            host_port=args.host_port,
            data_dir=Path(temp_dir),
            cpus=args.cpus,
            memory=args.memory,
            extra_env={
                "RUNTIME_PREVIEW_ARTIFACT_TTL_SECONDS": str(args.preview_ttl),
                "RUNTIME_ARTIFACT_SWEEP_INTERVAL_SECONDS": str(args.sweep_interval),
                "RUNTIME_STATE_MEMORY_MAX_BYTES": str(args.budget_bytes),
                "RUNTIME_STATE_MEMORY_MAX_ITEM_BYTES": str(args.item_bytes),
            },
        )
        started = time.monotonic()
        samples: list[dict[str, Any]] = []
        try:
            container.start()
            api = ApiClient(container.base_url)
            drill = DrillContext(container, api)
            drill.bootstrap(page_sizes={"small": 8 * 1024, "medium": 256 * 1024, "large": 2 * 1024 * 1024})
            _sample(container, samples, "idle", started)

            failures: list[str] = []
            for round_index in range(args.rounds):
                for label in ("small", "medium", "large"):
                    _, preview_url = drill.create_project_preview()
                    if drill.probe_preview(preview_url) not in range(200, 400):
                        failures.append(f"round={round_index} preview={label} 代理访问失败")
                for factory in (drill.create_asset_preview, drill.create_template_preview):
                    _, preview_url = factory()
                    if drill.probe_preview(preview_url) not in range(200, 400):
                        failures.append(f"round={round_index} {factory.__name__} 代理访问失败")
                drill.create_build_job()
                _sample(container, samples, f"round-{round_index + 1}", started)

            # 重复刷新：连续创建同一页面的预览，验证 TTL + 清扫回收而非无限增长。
            for _ in range(args.refresh_times):
                drill.create_project_preview()
            refresh_peak = (container.runtime_metrics().get("approx_bytes") or 0)
            _sample(container, samples, "refresh-peak", started)
            print(f"[refresh] 重复刷新后的近似字节：{refresh_peak}")

            # 等待至少两轮清扫，观察过期回收与清扫耗时。
            time.sleep(args.sweep_interval * 2 + args.preview_ttl)
            _sample(container, samples, "after-sweep", started)

            metrics = container.runtime_metrics()
            report.update(
                {
                    "finished_at": datetime.now(tz=UTC).isoformat(),
                    "duration_seconds": round(time.monotonic() - started, 2),
                    "rounds": args.rounds,
                    "refresh_times": args.refresh_times,
                    "preview_ttl_seconds": args.preview_ttl,
                    "sweep_interval_seconds": args.sweep_interval,
                    "peak_approx_bytes": max(item.get("approx_bytes") or 0 for item in samples),
                    "refresh_peak_approx_bytes": refresh_peak,
                    "final_approx_bytes": metrics.get("approx_bytes"),
                    "final_active_keys": metrics.get("active_keys"),
                    "capacity_rejections": metrics.get("capacity_rejections"),
                    "sweep_count": metrics.get("sweep_count"),
                    "sweep_failures": metrics.get("sweep_failures"),
                    "max_last_sweep_seconds": max(
                        (item.get("last_sweep_seconds") or 0.0) for item in samples
                    ),
                    "request_failures": failures + ([f"api failures={api.failures}"] if api.failures else []),
                    "oom_killed": any(item["memory"]["oom_killed"] for item in samples),
                    "samples": samples,
                }
            )
        finally:
            container.stop()
    return report


def run_restart_drill(args: argparse.Namespace) -> dict[str, Any]:
    """重启演练：旧临时预览失效、新预览可用、持久数据保留、构建中断可解释。"""

    report: dict[str, Any] = {"mode": "restart-drill", "image": args.image}
    with tempfile.TemporaryDirectory(prefix="wp-lite-restart-") as temp_dir:
        container = LiteContainer(
            args.image,
            name=f"wp-lite-restart-{uuid.uuid4().hex[:8]}",
            host_port=args.host_port,
            data_dir=Path(temp_dir),
            extra_env={"RUNTIME_PREVIEW_ARTIFACT_TTL_SECONDS": "3600"},
        )
        try:
            container.start()
            api = ApiClient(container.base_url)
            drill = DrillContext(container, api)
            drill.bootstrap(page_sizes={"small": 4 * 1024})
            _, old_preview_url = drill.create_project_preview()
            report["old_preview_available_before_restart"] = drill.probe_preview(old_preview_url) in range(200, 400)
            build_job_id = drill.create_build_job()

            container.restart()

            report["old_preview_status_after_restart"] = drill.probe_preview(old_preview_url)
            _, new_preview_url = drill.create_project_preview()
            report["new_preview_status_after_restart"] = drill.probe_preview(new_preview_url)
            _, pages = drill.api.request("GET", f"/api/pages?project_id={drill.project_id}&page=1&page_size=50")
            report["persisted_page_count"] = len(pages.get("items", []) if isinstance(pages, dict) else pages)
            _, jobs = drill.api.request("GET", f"/api/projects/{drill.project_id}/build-jobs")
            report["build_jobs_after_restart"] = [
                {"id": item.get("id"), "status": item.get("status"), "error_message": item.get("error_message")}
                for item in (jobs if isinstance(jobs, list) else [])
            ]
            report["build_job_id"] = build_job_id
            report["runtime_state_after_restart"] = container.runtime_metrics()
            report["backfill_after_restart"] = _run_backfill_after_restart(drill)
        finally:
            container.stop()
    return report


def _run_backfill_after_restart(drill: "DrillContext") -> dict[str, Any]:
    """运行态被清空后创建并执行资源比例回填任务，验证领取只依赖数据库。"""

    _, asset = drill.api.request(
        "POST",
        f"/api/workspaces/{drill.workspace_id}/assets/content",
        body={
            "asset_type": "drawio",
            "name": f"drill_drawio_{uuid.uuid4().hex[:6]}",
            "original_name": "drill.drawio",
            "content": "<mxfile><diagram name=\"drill\"/></mxfile>",
            "tags": [],
        },
    )
    _, group = drill.api.request(
        "POST",
        f"/api/workspaces/{drill.workspace_id}/assets/render-hint-backfill-jobs",
        body={"asset_types": ["drawio"], "asset_ids": [int(asset["id"])], "mode": "preview"},
    )
    group_id = str(group["job_group_id"])
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        _, state = drill.api.request("GET", f"/api/asset-render-hint-backfill-job-groups/{group_id}")
        if state.get("status") not in {"pending", "running"}:
            jobs = state.get("jobs") or []
            return {
                "group_status": state.get("status"),
                "succeeded_count": state.get("succeeded_count"),
                "job_attempt_count": int(jobs[0]["attempt_count"]) if jobs else None,
                "job_status": jobs[0]["status"] if jobs else None,
            }
        time.sleep(2)
    return {"group_status": "timeout"}


def run_redis_drill(args: argparse.Namespace) -> dict[str, Any]:
    """真实 Redis 模式：短暂断连期间的降级行为与恢复后无残留部分 artifact。"""

    network = f"wp-lite-drill-net-{uuid.uuid4().hex[:6]}"
    redis_name = f"wp-lite-drill-redis-{uuid.uuid4().hex[:6]}"
    report: dict[str, Any] = {"mode": "redis-drill", "image": args.image, "redis_database": args.redis_database}
    with tempfile.TemporaryDirectory(prefix="wp-lite-redis-") as temp_dir:
        container = LiteContainer(
            args.image,
            name=f"wp-lite-redis-{uuid.uuid4().hex[:8]}",
            host_port=args.host_port,
            data_dir=Path(temp_dir),
            network=network,
            extra_env={
                "REDIS_URL": f"redis://{redis_name}:6379/{args.redis_database}",
                "REDIS_KEY_PREFIX": f"wp_lite_drill_{uuid.uuid4().hex[:6]}",
            },
        )
        try:
            docker("network", "create", network)
            docker(
                "run",
                "--detach",
                "--name",
                redis_name,
                "--network",
                network,
                "redis:7-alpine",
            )
            container.start()
            api = ApiClient(container.base_url)
            drill = DrillContext(container, api)
            drill.bootstrap(page_sizes={"small": 4 * 1024})
            _, healthy_preview_url = drill.create_project_preview()
            report["preview_before_disconnect"] = drill.probe_preview(healthy_preview_url) in range(200, 400)

            docker("stop", redis_name)
            time.sleep(3)
            report["readyz_while_disconnected"] = container.backend_probe(
                f"http://127.0.0.1:{BACKEND_PROBE_PORT}/readyz"
            )
            status, payload = api.request_ignoring_status("POST", f"/api/projects/{drill.project_id}/preview-artifacts", body={"entry_descriptor": {"entry_type": "route", "route": drill.entry_route}})
            report["preview_create_status_while_disconnected"] = status
            report["preview_create_error_while_disconnected"] = (
                payload.get("code") if isinstance(payload, dict) else str(payload)[:120]
            )
            report["read_status_while_disconnected"] = drill.probe_preview(healthy_preview_url)

            docker("start", redis_name)
            time.sleep(5)
            _, recovered_preview_url = drill.create_project_preview()
            report["preview_after_recovery"] = drill.probe_preview(recovered_preview_url) in range(200, 400)
            metrics = container.runtime_metrics()
            report["metrics_after_recovery"] = metrics
            report["redis_keys_after_recovery"] = docker(
                "exec", redis_name, "redis-cli", "-n", str(args.redis_database), "dbsize"
            ).stdout.strip()
        finally:
            container.stop()
            docker("rm", "--force", redis_name, check=False)
            docker("network", "rm", network, check=False)
    return report


def _write_report(report: dict[str, Any]) -> Path:
    """写出 JSON 报告，便于复现与对比。"""

    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    path = REPORT_ROOT / f"{report['mode']}-{timestamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[report] 已写入 {path.relative_to(REPO_ROOT)}")
    return path


def main() -> int:
    """解析参数并执行指定演练模式。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=["baseline", "restart-drill", "redis-drill"])
    parser.add_argument("--image", required=True)
    parser.add_argument("--host-port", type=int, default=18080)
    parser.add_argument("--cpus", default="2")
    parser.add_argument("--memory", default="4g")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--refresh-times", type=int, default=120)
    parser.add_argument("--preview-ttl", type=int, default=30)
    parser.add_argument("--sweep-interval", type=int, default=5)
    parser.add_argument("--budget-bytes", type=int, default=134217728)
    parser.add_argument("--item-bytes", type=int, default=16777216)
    parser.add_argument("--redis-database", type=int, default=14)
    args = parser.parse_args()

    runners = {
        "baseline": run_baseline,
        "restart-drill": run_restart_drill,
        "redis-drill": run_redis_drill,
    }
    report = runners[args.mode](args)
    _write_report(report)
    print(json.dumps(report, ensure_ascii=False, indent=2)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
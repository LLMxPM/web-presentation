"""文件功能：创建架构演练专用 Docker Compose 拓扑，所有数据、端口与凭证均隔离。"""

from __future__ import annotations

import base64
import json
import secrets
import socket
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]


def command(*args: str, timeout: int = 180) -> str:
    """执行参数数组，不经过 shell；调用者不得把凭证作为命令行参数。"""
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(f"{args[0]} 执行失败：{result.stderr[-2500:]} {result.stdout[-2500:]}")
    return result.stdout.strip()


def free_port() -> int:
    """从本机回环分配空闲端口，Compose 只绑定 127.0.0.1。"""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class DockerDrill:
    """通过专属项目文件操作容器，禁止使用开发服务或任意外部 Compose。"""

    def __init__(self, directory: Path) -> None:
        """加载带所有权标记的测试上下文；路径必须位于根仓 .tmp/docker-architecture。"""
        self.directory = directory.resolve()
        if not self.directory.is_relative_to(ROOT / ".tmp" / "docker-architecture"):
            raise ValueError("演练目录必须位于 .tmp/docker-architecture")
        self.context = json.loads((self.directory / "context.json").read_text(encoding="utf-8"))
        self.project = self.context["project"]
        if not self.project.startswith("wp-arch-drill-"):
            raise ValueError("无效的演练项目所有权标记")
        self.output = (ROOT / self.context["output"]).resolve()
        if not self.output.is_relative_to(ROOT / "test-results" / "docker-architecture") or self.output.name != self.project:
            raise ValueError("无效的演练证据目录")

    def compose(self, *args: str, timeout: int = 180) -> str:
        """所有变更仅作用于本次随机命名的 Compose 项目。"""
        return command("docker", "compose", "-p", self.project, "-f", str(self.directory / "compose.json"), *args, timeout=timeout)

    def container(self, service: str) -> str:
        """读取本项目服务 ID，避免名称猜测命中其它容器。"""
        value = self.compose("ps", "-aq", service)
        if not value or "\n" in value:
            raise RuntimeError(f"无法唯一定位测试服务 {service}")
        return value

    def wait_http(self, origin: str, path: str, seconds: int = 90) -> None:
        """只轮询上下文中的回环服务，达到期限后失败。"""
        if not origin.startswith("http://127.0.0.1:"):
            raise ValueError("探针只允许回环隔离服务")
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                with urlopen(origin + path, timeout=2) as response:
                    if response.status == 200:
                        return
            except (URLError, TimeoutError, OSError):
                time.sleep(0.5)
                continue
            time.sleep(0.5)
        raise TimeoutError(f"测试服务未就绪：{path}")

    def save(self, name: str, data: object) -> None:
        """写入脱敏的小型 JSON 证据，禁止写入上下文凭证。"""
        if Path(name).name != name:
            raise ValueError("证据名称不能包含目录")
        (self.output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def snapshot(self) -> None:
        """逐阶段记录实际容器、镜像与拓扑，不把尚未启动的 Renderer 记作已就绪。"""
        raw = self.compose("ps", "--all", "--format", "json")
        containers = json.loads(raw) if raw.startswith("[") else [json.loads(line) for line in raw.splitlines() if line]
        image_ids = command("docker", "inspect", *[item["ID"] for item in containers], "--format", "{{.Image}}") if containers else ""
        topology = [{"service": item["Service"], "state": item["State"], "health": item.get("Health"),
                     "image": item["Image"], "image_id": image_id}
                    for item, image_id in zip(containers, image_ids.splitlines(), strict=True)]
        revision = command("docker", "exec", self.container("postgres"), "psql", "-U", "drill", "-d", "architecture_e2e",
                           "-tAc", "SELECT version_num FROM alembic_version")
        self.save("environment.json", {"project": self.project, "candidate": self.context["candidate"],
                                      "images": self.context["images"], "topology": topology,
                                      "database_revision": revision,
                                      "docker": command("docker", "info", "--format", "{{.OSType}}/{{.Architecture}} {{.NCPU}} CPUs {{.MemTotal}} bytes")})


def create_environment(backend_image: str, runtime_image: str, renderer_image: str, *, defer_renderer: bool = False, fault_injection: bool = False) -> DockerDrill:
    """固定镜像 ID，创建双 Backend/预览/构建/Renderer 与单 Check 的独立环境。"""
    project = "wp-arch-drill-" + secrets.token_hex(4)
    directory = ROOT / ".tmp" / "docker-architecture" / project
    directory.mkdir(parents=True)
    output = Path("test-results/docker-architecture") / project
    (ROOT / output).mkdir(parents=True)
    ports = {key: free_port() for key in ("gateway", "backend_a", "backend_b", "mock", "gate")}
    origins = {key: f"http://127.0.0.1:{port}" for key, port in ports.items()}
    password = secrets.token_urlsafe(24)
    render_secret = secrets.token_urlsafe(36)
    build_secret = secrets.token_urlsafe(36)
    ai_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    images = {name: command("docker", "image", "inspect", image, "--format", "{{.Id}}") for name, image in (
        ("backend", backend_image), ("runtime", runtime_image))}
    images["renderer"] = None if defer_renderer else command("docker", "image", "inspect", renderer_image, "--format", "{{.Id}}")
    backend_env = {
        "DATABASE_URL": "postgresql+asyncpg://drill:drill-only@postgres:5432/architecture_e2e",
        "REDIS_URL": "redis://redis:6379/15", "REDIS_KEY_PREFIX": "web_presentation_e2e",
        "DEFAULT_ADMIN_PASSWORD": password, "AI_SECRET_ENCRYPTION_KEY": ai_key,
        "BACKEND_MULTI_INSTANCE": "true", "OBJECT_STORAGE_SHARED_VOLUME": "true",
        "RUNTIME_RSA_ALLOW_AUTO_GENERATE": "false", "RUNTIME_RSA_PRIVATE_KEY_FILE": "/app/backend/data/drill-key.pem",
        "RUNTIME_BUILD_WORKER_CREDENTIAL": build_secret, "RENDER_SERVICE_CREDENTIAL": render_secret,
        "RENDER_WORKERS_CONFIG": json.dumps([{"worker_id": f"renderer-{i}", "base_url": f"http://renderer_{i}:7400"} for i in (1, 2)]),
        "RENDER_GLOBAL_CONCURRENCY": "2", "RENDER_WORKSPACE_CONCURRENCY": "2",
        "RENDER_RUNTIME_NAVIGATION_BASE_URL": "http://gateway/runtime",
        "RENDER_RUNTIME_ASSET_BASE_URL": "http://gateway/runtime", "RENDER_PLATFORM_ASSET_BASE_URL": "http://gateway",
        "PAGE_SCREENSHOT_BACKEND_BASE_URL": "http://gateway",
        "RUNTIME_BASE_URL": "http://preview_a:7373", "RUNTIME_PREVIEW_BASE_URL": "http://preview_a:7373",
        "RUNTIME_CHECK_BASE_URL": "http://check:7373", "RUNTIME_PUBLIC_BASE_URL": origins["gateway"] + "/runtime",
        "BACKEND_PUBLIC_BASE_URL": origins["gateway"], "AI_MODEL_CATALOG_SYNC_ENABLED": "false",
        "AI_RUN_OWNER_TTL_SECONDS": "12", "AI_RUN_OWNER_HEARTBEAT_SECONDS": "2", "AI_RUN_OWNER_SWEEP_SECONDS": "1",
        "AI_AGENT_STREAM_IDLE_TIMEOUT_SECONDS": "120", "APP_RELOAD": "false", "ACCESS_LOG_ENABLED": "false",
    }
    runtime_env = {
        "RUNTIME_SERVER_BASE_PATH": "/runtime/", "RUNTIME_PUBLIC_BASE_URL": origins["gateway"] + "/runtime",
        "RUNTIME_BACKEND_API_BASE_URL": "http://backend_b:8000", "RUNTIME_PREVIEW_JWKS_URL": "http://backend_b:8000/.well-known/jwks.json",
        "RUNTIME_SERVER_ALLOWED_HOSTS": "gateway,preview_a,preview_b,check,build_a,build_b",
        "RUNTIME_ACCESS_LOG_ENABLED": "false", "RUNTIME_STANDALONE_PREVIEW_ENABLED": "false",
    }
    services = {
        "postgres": {"image": "postgres:16-alpine", "environment": {"POSTGRES_USER": "drill", "POSTGRES_PASSWORD": "drill-only", "POSTGRES_DB": "architecture_e2e"}, "volumes": ["pg:/var/lib/postgresql/data"], "healthcheck": {"test": ["CMD-SHELL", "pg_isready -U drill -d architecture_e2e"], "interval": "1s", "retries": 30}},
        "redis": {"image": "redis:7-alpine"},
        "init": {"image": images["backend"], "entrypoint": ["python", "-c"], "command": ["import os; from pathlib import Path; from cryptography.hazmat.primitives.asymmetric import rsa; from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,NoEncryption; p=Path('/app/backend/data/drill-key.pem'); p.write_bytes(rsa.generate_private_key(public_exponent=65537,key_size=2048).private_bytes(Encoding.PEM,PrivateFormat.PKCS8,NoEncryption())); p.chmod(0o600); p=Path('/secrets/build'); p.write_text(os.environ['BUILD_SECRET']); p.chmod(0o400)"], "environment": {"BUILD_SECRET": build_secret}, "volumes": ["data:/app/backend/data", "build_secret:/secrets"]},
        "mock": {"image": images["backend"], "entrypoint": ["python", "/drill/docker_architecture_mock.py"], "volumes": [f"{(ROOT / 'scripts/testing').as_posix()}:/drill:ro"], "ports": [f"127.0.0.1:{ports['mock']}:8090"]},
    }
    for suffix in ("a", "b"):
        services[f"backend_{suffix}"] = {"image": images["backend"], "working_dir": "/app/backend", "entrypoint": ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"], "environment": backend_env, "volumes": ["data:/app/backend/data"], "ports": [f"127.0.0.1:{ports['backend_' + suffix]}:8000"]}
        services[f"preview_{suffix}"] = {"image": images["runtime"], "environment": {**runtime_env, "RUNTIME_ROLE": "preview", "RUNTIME_INSTANCE_ID": "preview-" + suffix}}
        services[f"build_{suffix}"] = {"image": images["runtime"], "environment": {**runtime_env, "RUNTIME_ROLE": "build", "RUNTIME_INSTANCE_ID": "build-" + suffix, "RUNTIME_BUILD_WORKER_ID": "drill-build-" + suffix, "RUNTIME_BUILD_WORKER_CREDENTIAL_FILE": "/run/secrets/build"}, "volumes": ["build_secret:/run/secrets:ro"]}
    services["check"] = {"image": images["runtime"], "environment": {**runtime_env, "RUNTIME_ROLE": "check"}}
    for i in (1, 2):
        services[f"renderer_{i}"] = {"image": images["renderer"] or renderer_image, "environment": {"RENDER_WORKER_ID": f"renderer-{i}", "RENDER_SERVICE_CREDENTIAL": render_secret}}
    if fault_injection:
        backend_env.update(RENDER_REQUEST_TIMEOUT_SECONDS="20", RENDER_ATTEMPT_LEASE_SECONDS="6",
                           RENDER_UNKNOWN_RECONCILE_AFTER_SECONDS="3",
                           RENDER_WORKERS_CONFIG=json.dumps([{"worker_id": f"renderer-{i}", "base_url": f"http://gate:{8091+i}"} for i in (1, 2)]))
        services["gate"] = {"image": images["backend"], "entrypoint": ["python", "/drill/docker_architecture_gate.py"],
                            "volumes": [f"{(ROOT / 'scripts/testing').as_posix()}:/drill:ro"],
                            "ports": [f"127.0.0.1:{ports['gate']}:8091"]}
        for i in (1, 2):
            services[f"renderer_{i}"]["environment"]["RENDER_RESULT_TTL_SECONDS"] = "10"
    services["gateway"] = {"image": "nginx:1.28-alpine", "ports": [f"127.0.0.1:{ports['gateway']}:80"], "volumes": [f"{directory.as_posix()}/nginx.conf:/etc/nginx/conf.d/default.conf:ro"]}
    (directory / "compose.json").write_text(json.dumps({"services": services, "volumes": {name: {} for name in ("pg", "data", "build_secret")}}, indent=2), encoding="utf-8")
    (directory / "context.json").write_text(json.dumps({"project": project, "output": output.as_posix(), "origins": origins, "password": password, "images": images, "fault_injection": fault_injection, "candidate": command("git", "rev-parse", "HEAD")}, indent=2), encoding="utf-8")
    write_gateway(directory, "same")
    return DockerDrill(directory)


def write_gateway(directory: Path, mode: str) -> None:
    """同版强制轮询、跨版强制子请求走 B；记录 upstream，令牌和请求头均沿生产链路。"""
    target = "preview_b:7373" if mode == "cross" else "preview_pool"
    context = json.loads((directory / "context.json").read_text(encoding="utf-8"))
    fault_location = "location = /runtime/__preview { proxy_pass http://gate:8091; proxy_read_timeout 100s; }" if context.get("fault_injection") else ""
    text = f"""# 文件功能：隔离演练 Gateway，不作为生产模板。
map $http_upgrade $connection_upgrade {{ default upgrade; '' close; }}
upstream preview_pool {{ server preview_a:7373; server preview_b:7373; }}
server {{
 listen 80; access_log off; client_max_body_size 100m;
 {fault_location}
 location /runtime/ {{
  proxy_pass http://{target}; proxy_http_version 1.1; proxy_set_header Host gateway;
  proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection $connection_upgrade;
  proxy_buffering off; add_header X-Drill-Upstream $upstream_addr always;
 }}
 location / {{ proxy_pass http://backend_b:8000; proxy_set_header Host $http_host; proxy_buffering off; }}
}}
"""
    (directory / "nginx.conf").write_text(text, encoding="utf-8")

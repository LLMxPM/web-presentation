"""文件功能：构造 MCP 专属 Docker 生产组件拓扑，隔离数据库/Redis/卷/端口与凭证。"""

import base64
import json
import os
import secrets
import subprocess
import time
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[2]


def command(*arguments, check=True, timeout=180, include_stderr=False):
    """使用参数数组；失败不回显配置、日志、认证响应或 Secret。"""
    environment = {key: value for key, value in os.environ.items() if not key.startswith(("WP_", "MCP_"))}
    result = subprocess.run(arguments, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=environment)
    if check and result.returncode:
        raise RuntimeError(f"{arguments[0]} {arguments[1]} 失败，退出码 {result.returncode}")
    return (result.stdout + (result.stderr if include_stderr else "")).strip()


def write_keys(directory):
    """创建专属一天有效 TLS 证书和共享签名密钥；不修改系统信任。"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "platform.example.test")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("platform.example.test"),
            x509.DNSName("mcp.example.test"), x509.IPAddress(ip_address("127.0.0.1"))]), False).sign(key, hashes.SHA256()))
    (directory / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (directory / "key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    signing = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (directory / "signing.pem").write_bytes(signing.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (directory / "service-secret").write_text(secrets.token_urlsafe(40), encoding="utf-8")
    for path in directory.iterdir():
        path.chmod(0o444)  # 仅专属测试值；生产 Secret 权限不以 Windows 绑定挂载验收替代。


class McpDocker:
    """命令只作用于随机 Compose 项目；私有上下文不能打印或提交。"""

    def __init__(self, args):
        """固定实际镜像 ID，使用生产 MCP Compose 与主仓原始交付镜像。"""
        self.project = "wp-mcp-docker-" + secrets.token_hex(5)
        self.directory = ROOT / ".tmp/mcp-docker" / self.project
        self.directory.mkdir(parents=True)
        self.output = ROOT / "test-results/mcp-docker" / self.project
        self.output.mkdir(parents=True)
        write_keys(self.directory)
        self.mcp_repository = args.mcp_repository.resolve()
        self.images = {name: command("docker", "image", "inspect", image, "--format", "{{.Id}}") for name, image in (
            ("backend", args.backend_image), ("runtime", args.runtime_image), ("renderer", args.renderer_image), ("mcp", args.mcp_image))}
        self.database = "wp_oauth_test_mcp_docker_" + secrets.token_hex(4)
        self.write_compose()

    def compose(self, *arguments, check=True):
        """固定项目、插值文件与两份 Compose，不读取开发环境配置。"""
        return command("docker", "compose", "--env-file", str(self.directory / "compose.env"), "-p", self.project,
            "-f", str(self.mcp_repository / "deploy/compose.yml"), "-f", str(self.directory / "overlay.json"),
            *arguments, check=check)

    def container(self, service):
        """服务必须唯一归属本次项目，禁止猜测开发容器名。"""
        value = self.compose("ps", "-aq", service)
        assert value and "\n" not in value
        return value

    def url(self, service, port):
        """只使用本次容器动态发布的回环端口。"""
        value = command("docker", "port", self.container(service), f"{port}/tcp")
        assert value.startswith("127.0.0.1:") and "\n" not in value
        return ("https://" if port == 443 else "http://") + value

    def wait(self, service, port, path, *, tls=None):
        """等待真实生产健康端点；不以 Nginx 静态 healthz 代替 Backend 就绪。"""
        url = self.url(service, port)
        with httpx.Client(trust_env=False, verify=tls or True, timeout=5,
                          headers={"Host": "mcp.example.test" if service == "gateway" else "platform.example.test"}) as client:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                try:
                    if client.get(url + path).status_code == 200:
                        return url
                except httpx.TransportError:
                    pass
                time.sleep(.4)
        raise RuntimeError("专属容器未就绪：" + service)

    def write_compose(self):
        """双 Backend 共用专属 PG/Redis/签名/卷，Runtime 与 Renderer 都为真实交付进程。"""
        directory = self.directory.as_posix()
        render_secret = secrets.token_urlsafe(40)
        backend = {"DATABASE_URL": f"postgresql+asyncpg://probe:probe-only@postgres:5432/{self.database}",
            "REDIS_URL": "redis://redis:6379/15", "REDIS_KEY_PREFIX": self.project,
            "DEFAULT_ADMIN_PASSWORD": secrets.token_urlsafe(32), "AI_SECRET_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
            "BACKEND_MULTI_INSTANCE": "true", "OBJECT_STORAGE_SHARED_VOLUME": "true", "RUNTIME_RSA_ALLOW_AUTO_GENERATE": "false",
            "RUNTIME_RSA_PRIVATE_KEY_FILE": "/probe-private/signing.pem", "RENDER_SERVICE_CREDENTIAL": render_secret,
            "RENDER_WORKERS_CONFIG": json.dumps([{"worker_id": "mcp-renderer", "base_url": "http://renderer:7400"}]),
            "RENDER_GLOBAL_CONCURRENCY": "1", "RENDER_WORKSPACE_CONCURRENCY": "1", "RUNTIME_BASE_URL": "http://runtime:7373",
            "RUNTIME_REQUEST_TIMEOUT_SECONDS": "30",
            # 浏览器在专属网络内使用内部 HTTP 产物地址；公网 OAuth/MCP 回源仍保留真实 TLS 校验。
            "RUNTIME_PUBLIC_BASE_URL": "http://backend_a/runtime", "BACKEND_PUBLIC_BASE_URL": "http://backend_a",
            "RENDER_RUNTIME_NAVIGATION_BASE_URL": "http://backend_a/runtime", "RENDER_RUNTIME_ASSET_BASE_URL": "http://backend_a/runtime",
            "RENDER_PLATFORM_ASSET_BASE_URL": "http://backend_a", "PAGE_SCREENSHOT_BACKEND_BASE_URL": "http://backend_a",
            "OAUTH_ENABLED": "true", "OAUTH_ISSUER": "https://platform.example.test", "OAUTH_EDITOR_ORIGIN": "https://platform.example.test",
            "OAUTH_MCP_RESOURCE": "https://mcp.example.test/mcp", "OAUTH_API_AUDIENCE": "https://platform.example.test/api/v1",
            "SESSION_SECURE": "true", "AI_MODEL_CATALOG_SYNC_ENABLED": "false", "APP_RELOAD": "false", "ACCESS_LOG_ENABLED": "false"}
        services = {"postgres": {"image": "postgres:16-alpine", "environment": {"POSTGRES_USER": "probe", "POSTGRES_PASSWORD": "probe-only", "POSTGRES_DB": self.database},
            "volumes": ["pg:/var/lib/postgresql/data"], "healthcheck": {"test": ["CMD-SHELL", "pg_isready -U probe"], "interval": "1s", "retries": 60}},
            "redis": {"image": "redis:7-alpine"},
            "runtime": {"image": self.images["runtime"], "environment": {"RUNTIME_ROLE": "all", "RUNTIME_SERVER_BASE_PATH": "/runtime/",
                "RUNTIME_PUBLIC_BASE_URL": "http://backend_a/runtime", "RUNTIME_BACKEND_API_BASE_URL": "http://backend_b:8000",
                "RUNTIME_PREVIEW_JWKS_URL": "http://backend_b:8000/.well-known/jwks.json", "RUNTIME_SERVER_ALLOWED_HOSTS": "backend_a,backend_b,runtime,platform.example.test",
                "RUNTIME_ACCESS_LOG_ENABLED": "false", "RUNTIME_STANDALONE_PREVIEW_ENABLED": "false"}},
            "renderer": {"image": self.images["renderer"], "environment": {"RENDER_WORKER_ID": "mcp-renderer", "RENDER_SERVICE_CREDENTIAL": render_secret}}}
        for suffix in ("a", "b"):
            services["backend_" + suffix] = {"image": self.images["backend"], "environment": {**backend, "PLATFORM_SIMPLE_RUN_MIGRATIONS": "true" if suffix == "a" else "false"},
                "volumes": ["data:/app/backend/data", f"{directory}:/probe-private", f"{(ROOT / 'scripts/testing').as_posix()}:/probe:ro"],
                "ports": ["127.0.0.1::8000"], "networks": {"default": {"aliases": ["backend"]}}}
        services["platform_tls"] = {"image": "nginx:1.28.3-alpine", "networks": {"default": {"aliases": ["platform.example.test"]}},
            "volumes": [f"{directory}/platform.conf:/etc/nginx/conf.d/default.conf:ro", f"{directory}:/probe-private:ro"], "ports": ["127.0.0.1::443"]}
        services["mcp"] = {"volumes": [f"{directory}:/probe-private:ro"]}
        (self.directory / "platform.conf").write_text('''# 文件功能：演练 TLS 外层，内层仍为两个平台镜像的生产 Nginx 配置。
upstream platforms { server backend_a:80; server backend_b:80; }
server { listen 443 ssl; server_name platform.example.test; ssl_certificate /probe-private/cert.pem;
ssl_certificate_key /probe-private/key.pem; access_log off; error_log /var/log/nginx/error.log crit;
location / { proxy_pass http://platforms; proxy_set_header Host $http_host; proxy_set_header X-Forwarded-Proto https;
proxy_buffering off; proxy_next_upstream off; proxy_read_timeout 75s; } }
''', encoding="utf-8")
        env = {"WP_MCP_BACKEND": "https://platform.example.test", "WP_MCP_BACKEND_CA_FILE": "/probe-private/cert.pem",
            "WP_MCP_ISSUER": "https://platform.example.test", "WP_MCP_RESOURCE": "https://mcp.example.test/mcp",
            "WP_MCP_API_AUDIENCE": "https://platform.example.test/api/v1", "WP_MCP_SERVICE_ID": "docker-mcp"}
        (self.directory / "mcp.env").write_text("\n".join(k + "=" + v for k, v in env.items()) + "\n", encoding="utf-8")
        variables = {"WP_MCP_IMAGE": self.images["mcp"], "WP_MCP_ENV_FILE": directory + "/mcp.env",
            "WP_MCP_SERVICE_SECRET_HOST_FILE": directory + "/service-secret", "MCP_PUBLIC_HOST": "mcp.example.test",
            "MCP_TLS_CERT_FILE": directory + "/cert.pem", "MCP_TLS_KEY_FILE": directory + "/key.pem", "MCP_TLS_PORT": "0"}
        (self.directory / "compose.env").write_text("\n".join(k + "=" + v for k, v in variables.items()) + "\n", encoding="utf-8")
        (self.directory / "overlay.json").write_text(json.dumps({"services": services, "volumes": {"pg": {}, "data": {}}}, indent=2), encoding="utf-8")

    def cleanup(self):
        """仅删除本次项目资源，保留忽略目录证据；不执行全局 prune。"""
        self.compose("down", "--volumes", "--remove-orphans")
        assert not command("docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + self.project)
        assert not command("docker", "volume", "ls", "-q", "--filter", "label=com.docker.compose.project=" + self.project)
        (self.output / "cleanup.json").write_text(json.dumps({"status": "passed", "project": self.project,
            "remaining_containers": 0, "remaining_volumes": 0}, indent=2), encoding="utf-8")

"""文件功能：用专属 loopback Nginx 和测试 TLS 证书消费独立 MCP 仓的真实网关模板。"""

import asyncio
import os
import socket
import ssl
import subprocess
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def write_certificate(directory):
    """生成仅本次测试信任的短期 loopback 证书，不写入系统证书库。"""
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "MCP gateway test")])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(private.public_key())
                   .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
                   .not_valid_after(now + timedelta(hours=1))
                   .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip_address("127.0.0.1"))]), critical=False)
                   .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True).sign(private, hashes.SHA256()))
    cert, key = directory / "cert.pem", directory / "key.pem"
    cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()))
    return cert, key


@asynccontextmanager
async def nginx_gateway(mcp_port):
    """只启动本次独立前缀的 Nginx；缺显式二进制/模板时不能计入网关验收。"""
    binary = os.getenv("WP_MCP_NGINX_BINARY", "")
    template = os.getenv("WP_MCP_GATEWAY_TEMPLATE", "")
    if not binary or not template:
        if os.getenv("WP_MCP_GATEWAY_REQUIRED") == "1":
            pytest.fail("真实 MCP Gateway 门禁必须配置 Nginx 二进制和独立仓模板")
        pytest.skip("未配置独立 MCP Gateway 真实二进制/模板")
    assert Path(binary).is_file() and Path(template).is_file()
    root = Path(__file__).resolve().parents[3]
    temporary_root = root / ".tmp" / "mcp-gateway"
    temporary_root.mkdir(parents=True, exist_ok=True)
    # 仅在明确仓库 .tmp 内创建/清理本次目录，避免干预系统或开发 Nginx。
    with tempfile.TemporaryDirectory(prefix="run-", dir=temporary_root) as temporary:
        directory = Path(temporary).resolve()
        assert directory.is_relative_to(temporary_root.resolve())
        (directory / "logs").mkdir()
        (directory / "temp").mkdir()
        cert, key = write_certificate(directory)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        config = Path(template).read_text(encoding="utf-8")
        config = (config.replace("${MCP_PUBLIC_HOST}", "mcp.example.test")
                  .replace("server mcp:8765", f"server 127.0.0.1:{mcp_port}")
                  .replace("listen 443 ssl", f"listen 127.0.0.1:{port} ssl")
                  .replace("/run/tls/cert.pem", cert.as_posix()).replace("/run/tls/key.pem", key.as_posix())
                  .replace("/var/log/nginx/access.log", "logs/access.log").replace("/var/log/nginx/error.log", "logs/error.log"))
        (directory / "nginx.conf").write_text("worker_processes 1; worker_shutdown_timeout 5s; pid logs/nginx.pid; events {worker_connections 64;} http {\n" + config + "\n}", encoding="utf-8")
        command = [binary, "-p", directory.as_posix() + "/", "-c", "nginx.conf"]
        checked = subprocess.run([*command, "-t"], capture_output=True, timeout=10)
        assert checked.returncode == 0, checked.stderr.decode(errors="replace")
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        context = ssl.create_default_context(cafile=cert)
        endpoint = f"https://127.0.0.1:{port}"
        try:
            async with httpx.AsyncClient(verify=context, trust_env=False, headers={"Host": "mcp.example.test"}) as client:
                async with asyncio.timeout(10):
                    while True:
                        try:
                            if (await client.get(endpoint + "/health/live")).status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        await asyncio.sleep(.05)
            yield endpoint, context, directory
        finally:
            subprocess.run([*command, "-s", "quit"], check=True, capture_output=True, timeout=10)
            await asyncio.to_thread(process.wait, 10)

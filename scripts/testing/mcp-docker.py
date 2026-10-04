"""文件功能：运行隔离 MCP Docker 创作验收，记录脱敏证据并清理本次专属容器/卷。"""

import argparse
import asyncio
import json
import ssl
import time
from pathlib import Path

from mcp_docker_cases import access_tokens, creation, revoked
from mcp_docker_env import ROOT, McpDocker, command


async def run(drill):
    """串行启动迁移与首个管理员，再启第二 Backend；使用真实生产进程和固定镜像。"""
    drill.compose("config", "--quiet")
    drill.compose("up", "-d", "--wait", "postgres", "redis")
    drill.compose("up", "-d", "runtime", "renderer", "backend_a")
    drill.wait("backend_a", 8000, "/healthz")
    drill.compose("up", "-d", "backend_b", "platform_tls")
    drill.wait("backend_b", 8000, "/healthz")
    command("docker", "exec", drill.container("backend_a"), "python", "-c",
        "exec(compile(open('/probe/mcp_docker_seed.py', encoding='utf-8').read(), '/probe/mcp_docker_seed.py', 'exec'))")
    credentials = json.loads((drill.directory / "credentials.json").read_text(encoding="utf-8"))
    tokens = await access_tokens(drill, credentials)
    drill.compose("up", "-d", "--wait", "--wait-timeout", "90", "mcp", "gateway")
    tls = ssl.create_default_context(cafile=str(drill.directory / "cert.pem"))
    endpoint = drill.wait("gateway", 443, "/health/ready", tls=tls)
    evidence = {"schema": "mcp-docker-evidence.v1", "status": "passed", "candidate": command("git", "rev-parse", "HEAD"),
        "mcp_candidate": command("git", "-C", str(drill.mcp_repository), "rev-parse", "HEAD"), "images": drill.images,
        "topology": "TLS Gateway / MCP / two Backend / PostgreSQL / Redis / Runtime / Renderer",
        "consent": "fixture-approved; not real ChatGPT consent"}
    evidence.update(await creation(drill, endpoint, tls, credentials, tokens))
    revocation, rotated = await revoked(drill, endpoint, tls, credentials, tokens)
    evidence.update(revocation)
    evidence["dependencies"] = {service: command("docker", "inspect", "--format", "{{.Image}}", drill.container(service))
        for service in ("postgres", "redis", "gateway")}
    evidence["docker_engine"] = command("docker", "version", "--format", "{{.Server.Version}}")
    evidence["postgresql"] = command("docker", "exec", drill.container("postgres"), "psql", "--version")
    evidence["redis"] = command("docker", "exec", drill.container("redis"), "redis-server", "--version")
    evidence["probe"] = "source-working-tree"
    # 检查容器 stdout/stderr 都没有本轮凭证，不展示完整生产日志。
    sensitive = [item[key] for item in credentials for key in ("code", "verifier", "password")]
    sensitive += [value for token in tokens for key, value in token.items() if key in {"access_token", "refresh_token"}]
    sensitive += rotated
    sensitive.append((drill.directory / "service-secret").read_text(encoding="utf-8"))
    for service in ("backend_a", "backend_b", "mcp", "gateway", "platform_tls"):
        logs = command("docker", "logs", drill.container(service), include_stderr=True)
        assert all(secret not in logs for secret in sensitive), "容器日志包含测试凭证"
    (drill.output / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    """显式输入四种交付镜像，不复用开发数据库；失败也完成本次项目清理。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcp-repository", type=Path, default=ROOT.parent / "web-presentation-mcp")
    parser.add_argument("--backend-image", required=True)
    parser.add_argument("--runtime-image", required=True)
    parser.add_argument("--renderer-image", required=True)
    parser.add_argument("--mcp-image", required=True)
    args = parser.parse_args()
    drill = McpDocker(args)
    started = time.monotonic()
    print("专属演练目录：" + str(drill.directory), flush=True)
    try:
        asyncio.run(run(drill))
        print(f"MCP 容器生产组件链路通过，耗时 {time.monotonic()-started:.1f}s；证据：{drill.output}", flush=True)
    except Exception as error:
        (drill.output / ("failure-" + str(time.time_ns()) + ".json")).write_text(json.dumps({"status": "failed",
            "error_type": type(error).__name__}, indent=2), encoding="utf-8")
        raise
    finally:
        drill.cleanup()


if __name__ == "__main__":
    main()

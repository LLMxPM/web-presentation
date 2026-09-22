"""文件功能：在隔离容器中验证交付镜像的真实入口、健康端点与 Renderer 浏览器可启动性。"""
from __future__ import annotations

import argparse
import secrets
import subprocess
import time
import uuid


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """使用参数数组调用 Docker；只管理本脚本创建的容器，不暴露主机端口或挂载业务目录。"""

    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=45)


def health_command(variant: str) -> list[str]:
    """根据镜像携带的运行时选择探针，检查每个长期进程而非仅检查容器存活。"""

    if variant == "runtime":
        return ["node", "-e", "fetch('http://127.0.0.1:7373/__runtime_healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
    urls = ["http://127.0.0.1:7400/readyz"] if variant == "renderer" else [
        "http://127.0.0.1/healthz", "http://127.0.0.1:8000/healthz",
    ]
    if variant == "lite":
        urls.append("http://127.0.0.1:7373/__runtime_healthz")
    return ["python", "-c", f"import urllib.request; [urllib.request.urlopen(u, timeout=2).read() for u in {urls!r}]"]


def verify(image: str, variant: str) -> None:
    """启动临时镜像并等待健康；退出时始终清理本次容器，失败保留服务日志到标准错误。"""

    name = f"wp-image-smoke-{uuid.uuid4().hex[:12]}"
    options = [
        "run", "--detach", "--name", name, "--network", "none",
        "--add-host", "backend:127.0.0.1", "--add-host", "runtime:127.0.0.1",
        "--env", "DATABASE_URL=sqlite+aiosqlite:////app/backend/data/image_smoke.db",
        "--env", "REDIS_URL=memory://image-smoke", "--env", "AI_ENABLED=false",
        "--env", f"RENDER_SERVICE_CREDENTIAL={secrets.token_urlsafe(48)}",
        "--env", "RUNTIME_SERVER_BASE_PATH=/", image,
    ]
    try:
        docker(*options)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            state = docker("inspect", "--format", "{{.State.Running}}", name).stdout.strip()
            if state != "true":
                raise RuntimeError("容器入口在健康检查通过前退出。")
            if docker("exec", name, *health_command(variant), check=False).returncode == 0:
                break
            time.sleep(2)
        else:
            raise RuntimeError("镜像健康检查超过 120 秒。")
        if variant == "renderer":
            docker("exec", name, "python", "-c", "\n".join([
                "import asyncio",
                "from playwright.async_api import async_playwright",
                "async def check():",
                "    async with async_playwright() as p:",
                "        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])",
                "        await browser.close()",
                "asyncio.run(check())",
            ]))
        print(f"[image] {variant} 启动、健康与执行依赖验证通过")
    except Exception:
        print(docker("logs", "--tail", "120", name, check=False).stdout)
        print(docker("logs", "--tail", "120", name, check=False).stderr)
        raise
    finally:
        docker("rm", "--force", name, check=False)


def main() -> None:
    """读取已经构建的本地镜像标签，本命令不推送镜像。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--variant", required=True, choices=["full", "lite", "runtime", "renderer"])
    args = parser.parse_args()
    verify(args.image, args.variant)


if __name__ == "__main__":
    main()

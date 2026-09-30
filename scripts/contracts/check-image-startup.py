"""文件功能：验证隔离镜像入口；Renderer 经真实控制 API 截图并留存产物与镜像身份。"""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import subprocess
import time
import uuid
from pathlib import Path

from image_evidence import verify_renderer_fixture


def docker(
    *args: str, check: bool = True, timeout: int = 45
) -> subprocess.CompletedProcess[str]:
    """使用参数数组调用 Docker；只管理本脚本创建的容器，不暴露主机端口或挂载业务目录。"""

    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=check, timeout=timeout
    )


def health_command(variant: str) -> list[str]:
    """根据镜像携带的运行时选择探针，检查每个长期进程而非仅检查容器存活。"""

    if variant == "runtime":
        return [
            "node",
            "-e",
            "fetch('http://127.0.0.1:7373/__runtime_healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))",
        ]
    urls = (
        ["http://127.0.0.1:7400/readyz"]
        if variant == "renderer"
        else [
            "http://127.0.0.1/healthz",
            "http://127.0.0.1:8000/healthz",
        ]
    )
    if variant == "lite":
        urls.append("http://127.0.0.1:7373/__runtime_healthz")
    return [
        "python",
        "-c",
        f"import urllib.request; [urllib.request.urlopen(u, timeout=2).read() for u in {urls!r}]",
    ]


def verify_runtime_version(name: str) -> dict:
    """在裁剪后的镜像验证非空发布身份、真实模块/CSS 与跨版 HTTP/HMR 拒绝。"""

    script = r"""
const assert = require('node:assert/strict');
const net = require('node:net');
(async () => {
  const origin = 'http://127.0.0.1:7373';
  const health = await (await fetch(origin + '/__runtime_healthz')).json();
  assert(health.runtime_kit_version && health.build_id && health.build_id !== 'dev');
  const fingerprint = health.runtime_kit_version + '+' + health.build_id;
  const mount = (process.env.RUNTIME_SERVER_BASE_PATH || '/').replace(/\/+$/, '');
  const base = mount + '/__runtime_version/' + encodeURIComponent(fingerprint) + '/';
  const wrong = mount + '/__runtime_version/' + encodeURIComponent(fingerprint + '-wrong') + '/';
  for (const path of ['src/main.ts', 'src/styles/global.css', '@vite/client']) {
    const response = await fetch(origin + base + path);
    assert.equal(response.status, 200, path + ' 正常版本不可用');
    assert.equal(response.headers.get('x-runtime-version-fingerprint'), fingerprint);
    const body = await response.text();
    if (path === 'src/main.ts') assert(body.includes(base), '嵌套 import 缺版本路径');
    const rejected = await fetch(origin + wrong + path);
    assert.equal(rejected.status, 409);
    assert.equal((await rejected.json()).code, 'PREVIEW_VERSION_SKEW');
  }
  const upgrade = await new Promise((resolve, reject) => {
    const socket = net.connect(7373, '127.0.0.1');
    let data = '';
    socket.setTimeout(3000, () => { socket.destroy(); reject(Error('HMR 拒绝超时')); });
    socket.on('error', reject);
    socket.on('data', chunk => { data += chunk.toString(); });
    socket.on('close', () => resolve(data));
    socket.on('connect', () => socket.write(
      'GET ' + wrong + ' HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Protocol: vite-hmr\r\n\r\n'
    ));
  });
  assert(upgrade.includes('409 Conflict') && !upgrade.includes('101 Switching'));
  console.log(JSON.stringify({ fingerprint, base, http: 'passed', hmr: 'passed' }));
})().catch(error => { console.error(error); process.exit(1); });
"""
    return json.loads(docker("exec", name, "node", "-e", script, timeout=90).stdout)


def verify(image: str, variant: str, output: Path) -> None:
    """启动临时镜像并等待健康；退出时始终清理本次容器，失败保留服务日志到标准错误。"""

    name = f"wp-image-smoke-{uuid.uuid4().hex[:12]}"
    output.mkdir(parents=True, exist_ok=False)
    options = [
        "run",
        "--detach",
        "--name",
        name,
        "--network",
        "none",
        "--add-host",
        "backend:127.0.0.1",
        "--add-host",
        "runtime:127.0.0.1",
        "--env",
        "DATABASE_URL=sqlite+aiosqlite:////app/backend/data/image_smoke.db",
        "--env",
        "REDIS_URL=memory://image-smoke",
        "--env",
        "AI_ENABLED=false",
        "--env",
        f"AI_SECRET_ENCRYPTION_KEY={base64.urlsafe_b64encode(os.urandom(32)).decode()}",
        "--env",
        f"RENDER_SERVICE_CREDENTIAL={secrets.token_urlsafe(48)}",
        "--env",
        "RUNTIME_SERVER_BASE_PATH=/",
        image,
    ]
    try:
        docker(*options)
        # 使用已启动容器实际镜像 ID 查询，避免标签在探测期间移动导致证据失真。
        image_id = docker("inspect", "--format", "{{.Image}}", name).stdout.strip()
        metadata = json.loads(docker("image", "inspect", image_id).stdout)[0]
        evidence = {
            "variant": variant,
            "requested_image": image,
            "image_id": image_id,
            "repo_digests": metadata.get("RepoDigests", []),
            "os": metadata["Os"],
            "architecture": metadata["Architecture"],
            "health": "pending",
            "execution": "not_run",
        }
        (output / "image.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            state = docker(
                "inspect", "--format", "{{.State.Running}}", name
            ).stdout.strip()
            if state != "true":
                raise RuntimeError("容器入口在健康检查通过前退出。")
            if (
                docker("exec", name, *health_command(variant), check=False).returncode
                == 0
            ):
                break
            time.sleep(2)
        else:
            raise RuntimeError("镜像健康检查超过 120 秒。")
        if variant in {"runtime", "lite"}:
            evidence["runtime_version"] = verify_runtime_version(name)
            evidence["execution"] = "runtime_version_guard_passed"
        if variant == "renderer":
            probe = Path(__file__).with_name("renderer-image-probe.py")
            docker("cp", str(probe), f"{name}:/tmp/renderer-image-probe.py")
            docker("exec", name, "python", "/tmp/renderer-image-probe.py", timeout=75)
            docker("cp", f"{name}:/tmp/wp-image-evidence/.", str(output))
            verify_renderer_fixture((output / "page.png").read_bytes())
            evidence["execution"] = "renderer_control_api_capture_passed"
        evidence["health"] = "passed"
        (output / "image.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
        print(
            f"[image] {variant} 健康通过；执行检查={evidence['execution']}；证据={output}"
        )
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
    parser.add_argument(
        "--variant", required=True, choices=["full", "lite", "runtime", "renderer"]
    )
    parser.add_argument(
        "--output-dir", type=Path, help="本次新建证据目录，不允许覆盖旧记录"
    )
    args = parser.parse_args()
    output = (
        args.output_dir
        or Path("test-results/images") / f"{args.variant}-{uuid.uuid4().hex[:12]}"
    )
    verify(args.image, args.variant, output)


if __name__ == "__main__":
    main()

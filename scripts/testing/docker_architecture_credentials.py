"""文件功能：用镜像实际 CMD 验证 Worker 凭证缺失、文件不存在与空文件时启动拒绝。"""

from __future__ import annotations

import json
import secrets
import subprocess

from docker_architecture_env import DockerDrill, command


def credentials(drill: DockerDrill, variants: tuple[str, ...] = ("runtime", "renderer")) -> None:
    """无网络临时容器复用空 secret 卷，禁止读取或输出实际凭证内容。"""
    mounts = json.loads(command("docker", "inspect", drill.container("build_a"), "--format", "{{json .Mounts}}"))
    volume = next(item["Name"] for item in mounts if item["Destination"] == "/run/secrets")
    if not volume.startswith(drill.project + "_"):
        raise ValueError("secret 卷不属于演练项目")
    script = "from pathlib import Path; p=Path('/secrets/empty'); p.touch(exist_ok=True); assert p.stat().st_size == 0; p.chmod(0o400)"
    command("docker", "run", "--rm", "--network", "none", "--mount", f"type=volume,source={volume},target=/secrets",
            "--entrypoint", "python", drill.context["images"]["backend"], "-c", script)
    report = {"status": "running", "cases": []}
    filename = "credentials.json" if len(variants) == 2 else "credentials-runtime.json"
    drill.save(filename, report)
    try:
        for variant in variants:
            image = drill.context["images"][variant]
            if not image:
                raise ValueError("须先启动 renderer 阶段，不能以其它镜像替代")
            for mode in ("missing", "missing-file", "empty-file"):
                name = f"{drill.project}-credential-{secrets.token_hex(3)}"
                arguments = ["docker", "create", "--name", name, "--network", "none", "--mount", f"type=volume,source={volume},target=/run/secrets,readonly"]
                if variant == "runtime":
                    arguments.extend(("-e", "RUNTIME_ROLE=build", "-e", "RUNTIME_BACKEND_API_BASE_URL=http://unreachable.invalid"))
                    variable = "RUNTIME_BUILD_WORKER_CREDENTIAL_FILE"
                    marker = "Worker 无法启动"
                else:
                    variable = "RENDER_SERVICE_CREDENTIAL_FILE"
                    marker = "RENDER_SERVICE_CREDENTIAL"
                if mode != "missing":
                    arguments.extend(("-e", f"{variable}=/run/secrets/{'empty' if mode == 'empty-file' else 'does-not-exist'}"))
                command(*arguments, image)
                try:
                    command("docker", "start", name)
                    exit_code = int(command("docker", "wait", name, timeout=30))
                    # Docker logs 的异常输出可能走 stderr，仅读取并匹配，不打印正文。
                    result = subprocess.run(["docker", "logs", name], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, check=True)
                    logs = result.stdout + result.stderr
                    assert exit_code != 0 and marker in logs, f"{variant}/{mode} 未按凭证错误退出"
                    report["cases"].append({"variant": variant, "mode": mode, "image_id": image, "exit_code": exit_code,
                                            "credential_error_observed": True, "actual_image_cmd": True, "network": "none"})
                    drill.save(filename, report)
                finally:
                    command("docker", "rm", "-f", name)
        report["status"] = "passed"
    except Exception:
        report["status"] = "failed"
        raise
    finally:
        drill.save(filename, report)

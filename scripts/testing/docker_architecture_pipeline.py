"""文件功能：调用官方完整链路探针，安全展开 ZIP 并准备浏览器加载及真实独立任务样本。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from copy import deepcopy
from zipfile import ZipFile

from docker_architecture_cases import sql
from docker_architecture_env import ROOT, DockerDrill, command, write_gateway


def update_backend(drill: DockerDrill, image: str) -> None:
    """替换隔离控制面镜像并保留数据/密钥；先确认副本健康，再重新解析 Gateway 上游。"""
    image_id = command("docker", "image", "inspect", image, "--format", "{{.Id}}")
    path = drill.directory / "compose.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    for service in ("backend_a", "backend_b", "mock", "init"):
        config["services"][service]["image"] = image_id
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    drill.compose("up", "-d", "--force-recreate", "backend_a", "backend_b")
    for suffix in ("a", "b"):
        drill.wait_http(drill.context["origins"]["backend_" + suffix], "/healthz")
    drill.compose("restart", "gateway")
    drill.context["images"]["backend"] = image_id
    drill.context["candidate"] = command("git", "rev-parse", "HEAD")
    (drill.directory / "context.json").write_text(json.dumps(drill.context, indent=2), encoding="utf-8")
    drill.save("backend-image.json", {"image_id": image_id, "candidate": drill.context["candidate"]})


def update_runtime(drill: DockerDrill, image: str) -> None:
    """仅替换本演练的 Runtime 镜像并保留共享数据；更新后重新记录候选与精确镜像 ID。"""
    image_id = command("docker", "image", "inspect", image, "--format", "{{.Id}}")
    path = drill.directory / "compose.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    for role in ("preview_a", "preview_b", "build_a", "build_b", "check"):
        config["services"][role]["image"] = image_id
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    drill.compose("up", "-d", "--force-recreate", "preview_a", "preview_b", "build_a", "build_b", "check")
    drill.compose("restart", "gateway")
    drill.context["images"]["runtime"] = image_id
    drill.context["candidate"] = command("git", "rev-parse", "HEAD")
    (drill.directory / "context.json").write_text(json.dumps(drill.context, indent=2), encoding="utf-8")
    drill.save("runtime-image.json", {"image_id": image_id, "candidate": drill.context["candidate"]})


def browser(drill: DockerDrill, mode: str, other_runtime_image: str | None = None) -> None:
    """浏览器从正常 iframe 入口导航，跨版只变更测试副本身份及 Gateway 分发。"""
    path = drill.directory / "compose.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    original = deepcopy(config["services"]["preview_b"])
    environment = config["services"]["preview_b"]["environment"]
    other_id = None
    if mode == "cross":
        if other_runtime_image:
            other_id = command("docker", "image", "inspect", other_runtime_image, "--format", "{{.Id}}")
            config["services"]["preview_b"]["image"] = other_id
            environment.pop("RUNTIME_BUILD_ID", None)
        else:
            environment["RUNTIME_BUILD_ID"] = "docker-drill-other-release"
    else:
        environment.pop("RUNTIME_BUILD_ID", None)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    try:
        if mode in ("same", "cross"):
            drill.compose("up", "-d", "--force-recreate", "preview_b")
            # 复建会改变容器 IP，重启专属 Gateway 重新解析上游地址。
            write_gateway(drill.directory, mode)
            drill.compose("restart", "gateway")
            drill.wait_http(drill.context["origins"]["gateway"], "/healthz")
        print(command("node", str(ROOT / "scripts/testing/docker-architecture-browser.mjs"), str(drill.directory), mode, timeout=90), flush=True)
        if mode == "cross":
            report = json.loads((drill.output / "browser-cross.json").read_text(encoding="utf-8"))
            report.update(cross_mode="older_image" if other_id else "identity_override", other_runtime_image_id=other_id)
            drill.save("browser-cross.json", report)
    finally:
        if mode == "cross":
            config["services"]["preview_b"] = original
            path.write_text(json.dumps(config, indent=2), encoding="utf-8")
            drill.compose("up", "-d", "--force-recreate", "preview_b")
            write_gateway(drill.directory, "same")
            drill.compose("restart", "gateway")


def pipeline(drill: DockerDrill, data: dict) -> None:
    """完成真实截图 PNG 与构建 ZIP 下载；入口浏览器加载另由 browser-build 阶段执行。"""
    folder = drill.output / ("pipeline" if not (drill.output / "pipeline").exists() else f"pipeline-{time.time_ns()}")
    env = {**os.environ, "WP_SMOKE_USERNAME": "admin", "WP_SMOKE_PASSWORD": drill.context["password"]}
    result = subprocess.run([sys.executable, str(ROOT / "scripts/contracts/check-deployment-pipeline.py"),
                             "--base-url", drill.context["origins"]["gateway"], "--page-id", str(data["page_id"]),
                             "--project-id", str(data["project_id"]), "--output-dir", str(folder), "--timeout", "180"],
                            env=env, capture_output=True, text=True, encoding="utf-8", timeout=420, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr[-2400:])
    print(result.stdout, flush=True)
    destination = folder / "build-site"
    destination.mkdir(exist_ok=False)
    with ZipFile(folder / "build.zip") as archive:
        total = 0
        for entry in archive.infolist():
            target = (destination / entry.filename).resolve()
            total += entry.file_size
            if not target.is_relative_to(destination.resolve()) or total > 256 * 1024 * 1024:
                raise ValueError("ZIP 路径或解压大小超过演练边界")
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(entry))
    report = json.loads((folder / "pipeline.json").read_text(encoding="utf-8"))
    build_id = report["build_job_id"]
    jobs = sql(drill, f"SELECT coalesce(json_agg(t),'[]'::json) FROM (SELECT id,status,attempt_id,attempt_count,lease_owner,claimed_at FROM project_build_jobs WHERE id={int(build_id)}) t")
    drill.save("pipeline-workers.json", jobs)
    drill.save("pipeline-current.json", {"directory": folder.relative_to(drill.output).as_posix(),
                                        "build_site": destination.relative_to(drill.output).as_posix()})

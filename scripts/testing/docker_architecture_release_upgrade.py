"""文件功能：在专属 Docker 演练项目中停旧、迁移并切换到候选三镜像，保留旧库与产物。"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from docker_architecture_env import DockerDrill, command
from docker_architecture_pipeline import wait_runtime

APP_SERVICES = (
    "gateway", "backend_a", "backend_b", "preview_a", "preview_b", "check", "build_a", "build_b",
    "renderer_1", "renderer_2",
)


def revision(drill: DockerDrill) -> str:
    """读取本演练 PostgreSQL 的真实迁移版本，不访问开发库。"""
    return command("docker", "exec", drill.container("postgres"), "psql", "-U", "drill", "-d", "architecture_e2e",
                   "-tAc", "SELECT version_num FROM alembic_version")


def verify_actual_images(drill: DockerDrill, images: dict[str, str]) -> None:
    """核对已运行容器的实际 image ID，避免只凭 Compose 配置宣称升级完成。"""
    groups = (("backend", ("backend_a", "backend_b")),
              ("runtime", ("preview_a", "preview_b", "check", "build_a", "build_b")),
              ("renderer", ("renderer_1", "renderer_2")))
    for role, services in groups:
        for service in services:
            actual = command("docker", "inspect", drill.container(service), "--format", "{{.Image}}")
            if actual != images[role]:
                raise AssertionError(f"{service} 实际镜像与候选 {role} 不一致")


def upgrade(drill: DockerDrill, backend_image: str, runtime_image: str, renderer_image: str) -> None:
    """先排空旧应用，再以前滚迁移和候选镜像恢复同一库、资源卷及受保护产物。"""
    if (drill.output / "release-upgrade-before.json").exists():
        raise RuntimeError("本项目已有升级记录；超时后使用 --resume，不得重跑迁移")
    active = command("docker", "exec", drill.container("postgres"), "psql", "-U", "drill", "-d", "architecture_e2e",
                     "-tAc", "SELECT count(*) FROM render_attempts WHERE active_occupancy=1")
    if active != "0":
        raise RuntimeError("仍有执行中的渲染 attempt，禁止排空升级")
    images = {name: command("docker", "image", "inspect", image, "--format", "{{.Id}}")
              for name, image in (("backend", backend_image), ("runtime", runtime_image),
                                  ("renderer", renderer_image))}
    before = {"images": drill.context["images"].copy(), "database_revision": revision(drill)}
    drill.save("release-upgrade-before.json", before)
    started = time.monotonic()
    drill.compose("stop", *APP_SERVICES)
    path = drill.directory / "compose.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    for name in ("backend_a", "backend_b"):
        config["services"][name]["image"] = images["backend"]
    for name in ("preview_a", "preview_b", "check", "build_a", "build_b"):
        config["services"][name]["image"] = images["runtime"]
    for name in ("renderer_1", "renderer_2"):
        config["services"][name]["image"] = images["renderer"]
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    drill.compose("run", "--rm", "--no-deps", "--entrypoint", "alembic", "backend_a", "upgrade", "head")
    migrated = revision(drill)
    drill.compose("up", "-d", "--force-recreate", *APP_SERVICES[1:])
    for name in ("backend_a", "backend_b"):
        drill.wait_http(drill.context["origins"][name], "/healthz")
    for name in ("preview_a", "preview_b", "check", "build_a", "build_b"):
        wait_runtime(drill, name)
    drill.compose("up", "-d", "--force-recreate", "gateway")
    drill.wait_http(drill.context["origins"]["gateway"], "/healthz")
    verify_actual_images(drill, images)
    drill.context["images"] = images
    drill.context["candidate"] = command("git", "rev-parse", "HEAD")
    (drill.directory / "context.json").write_text(json.dumps(drill.context, ensure_ascii=False, indent=2), encoding="utf-8")
    drill.snapshot()
    drill.save("release-upgrade.json", {"status": "passed", "before": before,
                                        "after": {"images": images, "database_revision": migrated},
                                        "elapsed_seconds": round(time.monotonic() - started, 2)})


def resume(drill: DockerDrill, backend_image: str, runtime_image: str, renderer_image: str) -> None:
    """迁移及容器重建已完成但本机就绪探针超时后，仅复核镜像、服务和迁移状态。"""
    images = {name: command("docker", "image", "inspect", image, "--format", "{{.Id}}")
              for name, image in (("backend", backend_image), ("runtime", runtime_image),
                                  ("renderer", renderer_image))}
    config = json.loads((drill.directory / "compose.json").read_text(encoding="utf-8"))
    for names, image in ((("backend_a", "backend_b"), images["backend"]),
                         (("preview_a", "preview_b", "check", "build_a", "build_b"), images["runtime"]),
                         (("renderer_1", "renderer_2"), images["renderer"])):
        if any(config["services"][name]["image"] != image for name in names):
            raise AssertionError("演练服务镜像与指定候选不一致")
    before = json.loads((drill.output / "release-upgrade-before.json").read_text(encoding="utf-8"))
    migrated = revision(drill)
    if migrated == before["database_revision"]:
        raise AssertionError("数据库尚未迁移，不能续验")
    for name in ("backend_a", "backend_b"):
        drill.wait_http(drill.context["origins"][name], "/healthz")
    for name in ("preview_a", "preview_b", "check", "build_a", "build_b"):
        wait_runtime(drill, name)
    drill.compose("up", "-d", "--force-recreate", "gateway")
    drill.wait_http(drill.context["origins"]["gateway"], "/healthz")
    verify_actual_images(drill, images)
    drill.context["images"] = images
    drill.context["candidate"] = command("git", "rev-parse", "HEAD")
    (drill.directory / "context.json").write_text(json.dumps(drill.context, ensure_ascii=False, indent=2), encoding="utf-8")
    drill.snapshot()
    drill.save("release-upgrade.json", {"status": "passed", "before": before,
                                        "after": {"images": images, "database_revision": migrated},
                                        "resumed_after_local_startup_timeout": True})


def main() -> None:
    """只接受带所有权标记的演练目录和本地已解析镜像，避免触碰其它 Compose 项目。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--backend-image", required=True)
    parser.add_argument("--runtime-image", required=True)
    parser.add_argument("--renderer-image", required=True)
    parser.add_argument("--resume", action="store_true", help="迁移已完成，仅核对启动并恢复 Gateway")
    args = parser.parse_args()
    action = resume if args.resume else upgrade
    action(DockerDrill(args.directory), args.backend_image, args.runtime_image, args.renderer_image)


if __name__ == "__main__":
    main()

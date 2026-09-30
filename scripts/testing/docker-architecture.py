"""文件功能：编排可重跑的本地 Docker 架构演练，不重置开发数据库，不推送镜像。"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from docker_architecture_cases import owner_drill, seed
from docker_architecture_credentials import credentials
from docker_architecture_env import DockerDrill, command, create_environment
from docker_architecture_jobs import competing_jobs
from docker_architecture_migration import legacy
from docker_architecture_pipeline import (
    browser,
    pipeline,
    update_backend,
    update_runtime,
)


def setup(args) -> DockerDrill:
    """先启动依赖、创建密钥并由单独迁移容器升级，然后启动应用副本。"""
    drill = create_environment(args.backend_image, args.runtime_image, args.renderer_image, defer_renderer=args.defer_renderer)
    print(f"演练目录：{drill.directory}", flush=True)
    try:
        start_services(drill, args.defer_renderer)
        drill.snapshot()
    except Exception as exc:
        drill.save("setup-failure.json", {"status": "failed", "error_type": type(exc).__name__,
                                         "cleanup_directory": drill.directory.relative_to(drill.directory.parents[2]).as_posix()})
        raise
    return drill


def start_services(drill: DockerDrill, defer_renderer: bool) -> None:
    """串行完成数据库迁移与默认用户初始化，再启动可并行执行的业务副本。"""
    drill.compose("up", "-d", "--wait", "postgres", "redis", "mock")
    drill.compose("run", "--rm", "init")
    drill.compose("run", "--rm", "--entrypoint", "alembic", "backend_a", "upgrade", "head")
    services = ["backend_a", "preview_a", "preview_b", "check"]
    if not defer_renderer:
        services.extend(("renderer_1", "renderer_2"))
    drill.compose("up", "-d", *services)
    drill.wait_http(drill.context["origins"]["backend_a"], "/healthz")
    # 默认管理员初始化先由 A 完成，避免首次空库两个副本同时插入。
    drill.compose("up", "-d", "backend_b", "build_a", "build_b")
    drill.wait_http(drill.context["origins"]["backend_b"], "/healthz")
    drill.compose("up", "-d", "gateway")
    drill.wait_http(drill.context["origins"]["gateway"], "/healthz")


def main() -> None:
    """各阶段可独立重跑；cleanup 仅删除本次专属项目及其数据卷。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("setup", "backend", "renderer", "runtime", "seed", "owner", "owner-pause", "owner-hostname", "legacy", "browser-same", "browser-cross", "pipeline", "jobs", "credentials", "credentials-runtime", "browser-build", "cleanup"))
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--backend-image", default="wp-lite:drill")
    parser.add_argument("--runtime-image", default="wp-runtime:drill")
    parser.add_argument("--renderer-image", default="wp-renderer:drill")
    parser.add_argument("--other-runtime-image", help="browser-cross 使用真实旧 Runtime 镜像；省略时只覆盖测试发布身份")
    parser.add_argument("--defer-renderer", action="store_true", help="镜像构建期间先验证控制面；构建完成后执行 renderer 阶段")
    args = parser.parse_args()
    if args.phase != "setup" and args.directory is None:
        parser.error("后续阶段必须显式提供 --directory")
    drill = setup(args) if args.phase == "setup" else DockerDrill(args.directory)
    started = time.monotonic()
    try:
        if args.phase == "seed":
            seed(drill)
        elif args.phase == "renderer":
            image_id = command("docker", "image", "inspect", args.renderer_image, "--format", "{{.Id}}")
            path = drill.directory / "compose.json"
            config = json.loads(path.read_text(encoding="utf-8"))
            for index in (1, 2):
                config["services"][f"renderer_{index}"]["image"] = image_id
            path.write_text(json.dumps(config, indent=2), encoding="utf-8")
            drill.context["images"]["renderer"] = image_id
            (drill.directory / "context.json").write_text(json.dumps(drill.context, indent=2), encoding="utf-8")
            drill.compose("up", "-d", "renderer_1", "renderer_2")
            drill.save("renderer-image.json", {"image_id": image_id})
        elif args.phase.startswith("owner"):
            data = json.loads((drill.output / "seed.json").read_text(encoding="utf-8"))
            owner_drill(drill, data, mode=args.phase.removeprefix("owner-") if args.phase != "owner" else "kill")
        elif args.phase == "runtime":
            update_runtime(drill, args.runtime_image)
        elif args.phase == "backend":
            update_backend(drill, args.backend_image)
        elif args.phase == "legacy":
            legacy(drill)
        elif args.phase.startswith("browser-"):
            browser(drill, args.phase.removeprefix("browser-"), args.other_runtime_image)
        elif args.phase == "pipeline":
            data = json.loads((drill.output / "seed.json").read_text(encoding="utf-8"))
            pipeline(drill, data)
        elif args.phase == "jobs":
            data = json.loads((drill.output / "seed.json").read_text(encoding="utf-8"))
            competing_jobs(drill, data)
        elif args.phase.startswith("credentials"):
            credentials(drill, ("runtime",) if args.phase == "credentials-runtime" else ("runtime", "renderer"))
        elif args.phase == "cleanup":
            try:
                drill.snapshot()
            except RuntimeError as exc:
                # setup 未完成或上次已清理时也要允许删除专属项目，保留快照失败类型。
                drill.save("cleanup-snapshot.json", {"status": "unavailable", "error_type": type(exc).__name__})
            drill.compose("down", "--volumes", "--remove-orphans")
            containers = drill.compose("ps", "-aq").splitlines()
            volumes = command("docker", "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={drill.project}").splitlines()
            if containers or volumes:
                raise RuntimeError("专属项目仍有容器或数据卷未清理")
            drill.save("cleanup.json", {"status": "passed", "project": drill.project,
                                        "remaining_containers": containers, "remaining_volumes": volumes})
        if args.phase != "cleanup":
            drill.snapshot()
        print(f"阶段 {args.phase} 完成，耗时 {time.monotonic()-started:.1f}s；证据：{drill.output}", flush=True)
    except Exception as exc:
        drill.save(args.phase + "-failure.json", {"status": "failed", "error_type": type(exc).__name__, "elapsed_seconds": round(time.monotonic()-started, 3)})
        raise


if __name__ == "__main__":
    main()

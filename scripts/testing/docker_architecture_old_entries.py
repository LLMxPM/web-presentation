"""文件功能：验证完整旧 platform/Lite 产物，并在 N 应用上下载加载同一旧 ZIP；支持失败后定向续跑。"""

from __future__ import annotations

import json

from docker_architecture_artifacts import reload_old_artifact
from docker_architecture_env import DockerDrill, command
from docker_architecture_pipeline import wait_runtime
from docker_architecture_upgrade import wait_backend
from docker_architecture_upgrade_business import read_write
from docker_architecture_upgrade_env import switch_entry


def old_entries(drill: DockerDrill, *, runtime_n: str | None = None) -> list:
    """保持旧镜像源码/CMD；旧 Lite 的 Runtime 角色基址须能由远程 Renderer 访问，不能用容器回环。"""
    from docker_architecture_compatibility import browser_pipeline, renderer_image

    original_renderer = drill.context["images"]["renderer"]
    original_runtime = runtime_n or drill.context["images"]["runtime"]
    results = []
    try:
        renderer_image(drill, "wp-renderer-m05-4c7eee8:local")
        for role in ("platform", "lite"):
            label = "m05-full-old-" + role
            pipeline_path = drill.output / (label + "-pipeline.json")
            loaded_path = drill.output / ("m05-" + role + "-old-artifact-on-n.json")
            if pipeline_path.exists() and loaded_path.exists():
                saved = json.loads(pipeline_path.read_text(encoding="utf-8"))
                loaded = json.loads(loaded_path.read_text(encoding="utf-8"))
                expected_backend = drill.context["m05_images"]["platform_n"] if role == "platform" else drill.context["images"]["backend"]
                old_images = {"backend": drill.context["m05_images"][role], "runtime": drill.context["m05_images"]["runtime"] if role == "platform" else drill.context["m05_images"][role],
                              "renderer": command("docker", "image", "inspect", "wp-renderer-m05-4c7eee8:local", "--format", "{{.Id}}")}
                if (saved["status"] == loaded["status"] == "passed" and loaded["sha256"] == saved["build"]["sha256"]
                        and saved.get("images") == old_images and loaded.get("backend_image") == expected_backend):
                    results.append({"backend": "N-1", "runtime": "N-1", "renderer": "N-1", "dialect": role,
                                    "result": saved, "reused_evidence": loaded_path.name})
                    continue
            path = drill.directory / "compose.json"
            config = json.loads(path.read_text(encoding="utf-8"))
            if role == "platform":
                config["services"]["m05_runtime"]["image"] = drill.context["m05_images"]["runtime"]
                path.write_text(json.dumps(config, indent=2), encoding="utf-8")
                drill.compose("up", "-d", "--no-deps", "--force-recreate", "m05_runtime")
                wait_runtime(drill, "m05_runtime")
            else:
                config["services"]["m05_lite"]["environment"]["RUNTIME_PREVIEW_BASE_URL"] = "http://m05_lite:7373"
                path.write_text(json.dumps(config, indent=2), encoding="utf-8")
            switch_entry(drill, role, current=False, migrate=False)
            wait_backend(drill, role)
            data = json.loads((drill.output / ("m05-" + role + "-data.json")).read_text(encoding="utf-8"))
            result = browser_pipeline(drill, data, label, origin=drill.context["origins"]["m05_" + role])
            results.append({"backend": "N-1", "runtime": "N-1", "renderer": "N-1", "db": "N 保留补偿",
                            "dialect": role, "result": result})
            if role == "platform":
                config = json.loads(path.read_text(encoding="utf-8"))
                config["services"]["m05_runtime"]["image"] = original_runtime
                path.write_text(json.dumps(config, indent=2), encoding="utf-8")
                drill.compose("up", "-d", "--no-deps", "--force-recreate", "m05_runtime")
                wait_runtime(drill, "m05_runtime")
            switch_entry(drill, role, current=True, migrate=False)
            wait_backend(drill, role)
            read_write(drill, role, data, "new-after-old-artifact")
            reload_old_artifact(drill, data, result, role)
        drill.save("m05-old-entries.json", {"status": "passed", "cases": results})
        return results
    finally:
        renderer_image(drill, original_renderer)

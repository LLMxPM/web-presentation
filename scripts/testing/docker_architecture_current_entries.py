"""文件功能：在保留历史数据的 N platform/Lite 真实入口完成全 N 公共能力 PNG/ZIP 链路。"""

from __future__ import annotations

import json

from docker_architecture_artifacts import reload_old_artifact
from docker_architecture_compatibility import browser_pipeline, renderer_image
from docker_architecture_env import DockerDrill
from docker_architecture_pipeline import wait_runtime
from docker_architecture_upgrade import wait_backend
from docker_architecture_upgrade_env import switch_entry


def current_entries(drill: DockerDrill) -> None:
    """沿用前滚/回滚历史库，不重新播种；每种交付形态运行真实 CMD，浏览器只在 Renderer 执行。"""
    renderer_image(drill, drill.context["images"]["renderer"])
    path = drill.directory / "compose.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["services"]["m05_runtime"]["image"] = drill.context["images"]["runtime"]
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    drill.compose("up", "-d", "--no-deps", "--force-recreate", "m05_runtime")
    wait_runtime(drill, "m05_runtime")
    report = {"status": "running", "cases": []}
    for role in ("platform", "lite"):
        switch_entry(drill, role, current=True, migrate=False)
        wait_backend(drill, role)
        data = json.loads((drill.output / ("m05-" + role + "-data.json")).read_text(encoding="utf-8"))
        old_path = drill.output / ("m05-full-old-" + role + "-pipeline.json")
        old = json.loads(old_path.read_text(encoding="utf-8"))
        reload_old_artifact(drill, data, old, role)
        result = browser_pipeline(drill, data, "m05-full-n-" + role, origin=drill.context["origins"]["m05_" + role])
        report["cases"].append({"dialect": role, "backend": "N", "runtime": "N", "renderer": "N", "result": result})
        drill.save("m05-current-entries.json", report)
    report["status"] = "passed"
    drill.save("m05-current-entries.json", report)

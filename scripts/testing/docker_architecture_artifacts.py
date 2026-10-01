"""文件功能：应用切回 N 后重新下载并加载 N-1 ZIP，证明保留产物未被重建或替换。"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from docker_architecture_cases import Client
from docker_architecture_env import ROOT, DockerDrill, command


def reload_old_artifact(drill: DockerDrill, data: dict, old: dict, role: str) -> dict:
    """经 N 的真实认证产物接口下载旧 Job 的 ZIP，再从原解压目录以 HTTP 加载，核对摘要与 Kit。"""
    client = Client(drill, "m05_" + role)
    path = f"/api/projects/{data['project_id']}/build-jobs/{old['build_job_id']}/artifact"
    with client.opener.open(client.origin + path, timeout=30) as response:
        content = response.read(256 * 1024 * 1024 + 1)
    assert len(content) <= 256 * 1024 * 1024
    digest = hashlib.sha256(content).hexdigest()
    assert digest == old["build"]["sha256"] and len(content) == old["build"]["bytes"], "旧 ZIP 在应用切回后变化"
    seed_path = drill.output / "seed.json"
    latest_path = drill.output / "pipeline-current.json"
    original_seed, original_latest = seed_path.read_bytes(), latest_path.read_bytes()
    original_context = deepcopy(drill.context)
    try:
        seed_path.write_text(json.dumps(data), encoding="utf-8")
        latest_path.write_text(json.dumps({"directory": old["artifact_directory"], "build_site": old["build_site"]}), encoding="utf-8")
        drill.context["origins"]["gateway"] = client.origin
        (drill.directory / "context.json").write_text(json.dumps(drill.context, indent=2), encoding="utf-8")
        command("node", str(ROOT / "scripts/testing/docker-architecture-browser.mjs"), str(drill.directory), "build", timeout=90)
        browser = json.loads((drill.output / "browser-build.json").read_text(encoding="utf-8"))
        report = {"status": "passed", "backend": "N", "created_by": "N-1", "dialect": role,
                  "backend_image": command("docker", "inspect", drill.container("m05_" + role), "--format", "{{.Image}}"),
                  "build_job_id": old["build_job_id"], "sha256": digest, "bytes": len(content),
                  "unchanged": True, "browser": browser}
        drill.save("m05-" + role + "-old-artifact-on-n.json", report)
        return report
    finally:
        seed_path.write_bytes(original_seed)
        latest_path.write_bytes(original_latest)
        drill.context = original_context
        (drill.directory / "context.json").write_text(json.dumps(drill.context, indent=2), encoding="utf-8")

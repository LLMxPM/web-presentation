"""文件功能：经候选 Backend 重新下载上一发布版 ZIP，并在浏览器加载原始构建站点。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from docker_architecture_cases import Client
from docker_architecture_env import ROOT, DockerDrill, command
from docker_architecture_pipeline import prepare_build_site


def verify(drill: DockerDrill) -> None:
    """复用旧版基线的 Job 与文件，核对升级后接口返回字节和浏览器入口。"""
    upgrade = json.loads((drill.output / "release-upgrade.json").read_text(encoding="utf-8"))
    if upgrade.get("status") != "passed" or drill.context["images"] != upgrade["after"]["images"]:
        raise AssertionError("候选镜像升级尚未完成，不读取旧产物")
    old = json.loads((drill.output / "pipeline/pipeline.json").read_text(encoding="utf-8"))
    client = Client(drill)
    path = f"/api/projects/{old['project_id']}/build-jobs/{old['build_job_id']}/artifact"
    with client.opener.open(client.origin + path, timeout=30) as response:
        content = response.read(256 * 1024 * 1024 + 1)
    digest = hashlib.sha256(content).hexdigest()
    if len(content) != old["build"]["bytes"] or digest != old["build"]["sha256"]:
        raise AssertionError("升级后旧版 ZIP 字节或摘要变化")
    latest_path = drill.output / "pipeline-current.json"
    browser_path = drill.output / "browser-build.json"
    original_latest = latest_path.read_bytes()
    original_browser = browser_path.read_bytes() if browser_path.exists() else None
    try:
        with TemporaryDirectory(prefix="release-old-artifact-", dir=drill.output) as temporary:
            folder = Path(temporary)
            (folder / "build.zip").write_bytes(content)
            prepare_build_site(drill, folder)
            command("node", str(ROOT / "scripts/testing/docker-architecture-browser.mjs"), str(drill.directory), "build", timeout=90)
            browser = json.loads(browser_path.read_text(encoding="utf-8"))
            if browser.get("status") != "passed":
                raise AssertionError("重新下载的旧版 ZIP 浏览器加载失败")
            drill.save("release-old-artifact-on-candidate.json", {
                "status": "passed", "created_by": "v0.3.1", "served_by": drill.context["images"]["backend"],
                "build_job_id": old["build_job_id"], "sha256": digest, "bytes": len(content), "browser": browser,
            })
    finally:
        latest_path.write_bytes(original_latest)
        if original_browser is None:
            browser_path.unlink(missing_ok=True)
        else:
            browser_path.write_bytes(original_browser)


def main() -> None:
    """只加载本仓专属演练目录，避免读取开发环境的凭证和产物。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    verify(DockerDrill(args.directory))


if __name__ == "__main__":
    main()

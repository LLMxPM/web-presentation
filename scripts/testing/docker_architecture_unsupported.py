"""文件功能：对缺发布身份的旧 Runtime 分别记录真实截图失败、独立 ZIP 构建和浏览器加载。"""

from __future__ import annotations

import hashlib
import json
import time
from copy import deepcopy

from docker_architecture_cases import Client, sql
from docker_architecture_env import ROOT, DockerDrill, command
from docker_architecture_pipeline import prepare_build_site, update_backend


def unsupported_pipeline(drill: DockerDrill, data: dict, label: str) -> dict:
    """缩短本项目总期限至 20 秒，要求截图真实失败且无结果；构建 ZIP 单独验证，不能记为整链路成功。"""
    path = drill.directory / "compose.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    original = {role: deepcopy(config["services"][role]["environment"]) for role in ("backend_a", "backend_b")}
    report = {"status": "running", "supported": False, "request_timeout_seconds": 20,
              "images": {name: command("docker", "inspect", drill.container(service), "--format", "{{.Image}}")
                         for name, service in (("backend", "backend_a"), ("runtime", "preview_a"), ("renderer", "renderer_1"))}}
    client = Client(drill)
    job_id = None
    seed_path = drill.output / "seed.json"
    original_seed = seed_path.read_bytes()
    try:
        for role in original:
            config["services"][role]["environment"]["RENDER_REQUEST_TIMEOUT_SECONDS"] = "20"
        path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        update_backend(drill, drill.context["images"]["backend"])
        client = Client(drill)
        job_id = client.json(f"/api/pages/{data['page_id']}/screenshot-jobs", {})["id"]
        deadline = time.monotonic() + 100
        while time.monotonic() < deadline:
            job = client.json(f"/api/page-screenshot-jobs/{job_id}")
            if job["status"] not in ("pending", "running"):
                break
            time.sleep(.5)
        else:
            raise TimeoutError("旧 Runtime 截图未按缩短期限收敛")
        assert job["status"] == "failed", "不支持组合意外发布了截图"
        report["screenshot"] = {key: job[key] for key in ("id", "status", "attempt_count", "error_code")}
        requests = sql(drill, f"SELECT coalesce(json_agg(t),'[]'::json) FROM (SELECT id,status,result_id,error_code FROM render_requests WHERE page_id={int(data['page_id'])} AND created_at >= (SELECT created_at FROM page_screenshot_jobs WHERE id={int(job_id)})) t")
        assert requests and all(item["result_id"] is None and item["status"] in ("failed", "expired", "cancelled") for item in requests)
        report["requests"] = requests
        assert sql(drill, "SELECT count(*) FROM render_attempts WHERE active_occupancy=1") == 0
        build = client.json(f"/api/projects/{data['project_id']}/build-jobs", {"base_url": "./"})
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            build = client.json(f"/api/build-jobs/{build['id']}")
            if build["status"] not in ("pending", "running"):
                break
            time.sleep(.5)
        assert build["status"] == "succeeded", "旧 Runtime 独立构建未成功"
        with client.opener.open(client.origin + f"/api/projects/{data['project_id']}/build-jobs/{build['id']}/artifact", timeout=30) as response:
            content = response.read(256 * 1024 * 1024 + 1)
        digest = hashlib.sha256(content).hexdigest()
        assert digest == build["artifact_sha256"] and len(content) == build["artifact_size_bytes"]
        folder = drill.output / ("unsupported-build-" + str(time.time_ns()))
        folder.mkdir()
        (folder / "build.zip").write_bytes(content)
        prepare_build_site(drill, folder)
        seed_path.write_text(json.dumps(data), encoding="utf-8")
        command("node", str(ROOT / "scripts/testing/docker-architecture-browser.mjs"), str(drill.directory), "build", timeout=90)
        report["build"] = {"id": build["id"], "sha256": digest, "bytes": len(content), "directory": folder.name}
        report["browser"] = json.loads((drill.output / "browser-build.json").read_text(encoding="utf-8"))
        report.update(status="passed", scope="预期截图失败与独立构建验证通过；不支持预览/截图整链路")
        return report
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        if job_id is not None and client.json(f"/api/page-screenshot-jobs/{job_id}")["status"] in ("pending", "running"):
            client.json(f"/api/page-screenshot-jobs/{job_id}/cancel", {})
            deadline = time.monotonic() + 40
            while sql(drill, "SELECT count(*) FROM render_attempts WHERE active_occupancy=1"):
                if time.monotonic() >= deadline:
                    raise TimeoutError("失败场景取消后占用未释放，禁止换版")
                time.sleep(.5)
        seed_path.write_bytes(original_seed)
        for role, environment in original.items():
            config["services"][role]["environment"] = environment
        path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        update_backend(drill, drill.context["images"]["backend"])
        drill.save(label + "-unsupported.json", report)

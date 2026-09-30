"""文件功能：创建不同项目/页面的独立 Job，让双构建与双 Renderer 竞争并记录 attempt/槽位释放。"""

from __future__ import annotations

import hashlib
import io
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit
from urllib.request import Request
from zipfile import ZipFile

from docker_architecture_cases import Client, sql
from docker_architecture_env import DockerDrill


def download(client: Client, target: str, limit: int) -> bytes:
    """仅下载本次 Gateway 的有界产物，测试 Cookie 不发到跨源 URL。"""
    url = urljoin(client.origin + "/", target)
    if urlsplit(url)[:2] != urlsplit(client.origin)[:2]:
        raise ValueError("任务产物必须属于本演练 Gateway")
    with client.opener.open(Request(url), timeout=30) as response:
        content = response.read(limit + 1)
    if len(content) > limit:
        raise ValueError("任务产物超过演练下载上限")
    return content


def competing_jobs(drill: DockerDrill, data: dict) -> None:
    """同时创建四个独立构建与四个截图；保留运行期租约，不用终态空 owner 推断执行者。"""
    client = Client(drill)
    source = client.json(f"/api/pages/{data['page_id']}")["page_content"]
    targets = []
    for index in range(4):
        project = client.json("/api/projects", {"name": f"Independent job {time.time_ns()}-{index}", "workspace_id": data["workspace_id"]})
        page = client.json("/api/pages", {"title": f"Independent page {index}", "workspace_id": data["workspace_id"],
                                          "project_id": project["id"], "page_content": source})
        client.json(f"/api/projects/{project['id']}/routes", {"routes": [{"route_type": "page", "route": "probe", "order": 0, "page_id": page["id"]}]}, "PUT")
        targets.append({"project_id": project["id"], "page_id": page["id"]})
    report = {"status": "running", "targets": targets, "samples": [], "downloads": []}
    drill.save("jobs.json", report)

    def enqueue(target: dict) -> dict:
        """每个线程持有自己的 Cookie 会话，同一输入只有一次 API 入队。"""
        local = Client(drill)
        build = local.json(f"/api/projects/{target['project_id']}/build-jobs", {"base_url": "./"})
        screenshot = local.json(f"/api/pages/{target['page_id']}/screenshot-jobs", {})
        return {**target, "build_id": build["id"], "screenshot_id": screenshot["id"]}

    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            targets[:] = list(executor.map(enqueue, targets))
        build_ids = ",".join(str(item["build_id"]) for item in targets)
        screenshot_ids = ",".join(str(item["screenshot_id"]) for item in targets)
        page_ids = ",".join(str(item["page_id"]) for item in targets)
        assert len({item["build_id"] for item in targets}) == len({item["screenshot_id"] for item in targets}) == 4
        deadline = time.monotonic() + 240
        while True:
            builds = sql(drill, f"SELECT json_agg(t) FROM (SELECT id,status,attempt_id,attempt_count,lease_owner,claimed_at,started_at,finished_at FROM project_build_jobs WHERE id IN ({build_ids}) ORDER BY id) t")
            screenshots = sql(drill, f"SELECT json_agg(t) FROM (SELECT id,status,attempt_count,worker_id,started_at,finished_at FROM page_screenshot_jobs WHERE id IN ({screenshot_ids}) ORDER BY id) t")
            attempts = sql(drill, f"SELECT coalesce(json_agg(t),'[]'::json) FROM (SELECT a.id,a.request_id,a.attempt_uid,a.attempt_no,a.worker_id,a.status,a.active_occupancy,a.cleanup_status,a.started_at,a.finished_at FROM render_attempts a JOIN render_requests r ON r.id=a.request_id WHERE r.page_id IN ({page_ids}) AND r.logical_owner_key LIKE 'page-screenshot:%' ORDER BY a.id) t")
            report["samples"].append({"builds": builds, "screenshots": screenshots, "render_attempts": attempts})
            drill.save("jobs.json", report)
            states = [item["status"] for item in builds + screenshots]
            if any(state not in {"pending", "running", "succeeded"} for state in states):
                raise AssertionError("独立任务出现失败/取消终态，见 jobs.json")
            if all(state == "succeeded" for state in states) and attempts and all(not item["active_occupancy"] for item in attempts):
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("独立任务或 Renderer 槽位未在 240 秒内排空")
            time.sleep(0.5)
        build_workers = {item["lease_owner"] for sample in report["samples"] for item in sample["builds"] if item["lease_owner"]}
        render_workers = {item["worker_id"] for item in attempts}
        assert len(build_workers) == len(render_workers) == 2, "未证明双执行副本均参与独立任务"
        assert all(item["attempt_count"] == 1 for item in builds + screenshots), "本轮无故障竞争产生多次执行"
        assert len(attempts) == 4 and len({item["request_id"] for item in attempts}) == 4
        assert all(item["attempt_no"] == 1 and item["cleanup_status"] == "released" for item in attempts)
        for target in targets:
            page = client.json(f"/api/pages/{target['page_id']}")
            png = download(client, page["screenshot_url"], 32 * 1024 * 1024)
            assert page["screenshot_is_latest"] and png.startswith(b"\x89PNG\r\n\x1a\n")
            archive_bytes = download(client, f"/api/projects/{target['project_id']}/build-jobs/{target['build_id']}/artifact", 256 * 1024 * 1024)
            build = client.json(f"/api/build-jobs/{target['build_id']}")
            with ZipFile(io.BytesIO(archive_bytes)) as archive:
                assert b"<html" in archive.read(build["artifact_entry_file"]).lower()
            digest = hashlib.sha256(archive_bytes).hexdigest()
            assert digest == build["artifact_sha256"] and len(archive_bytes) == build["artifact_size_bytes"]
            report["downloads"].append({**target, "png_bytes": len(png), "png_sha256": hashlib.sha256(png).hexdigest(),
                                        "zip_bytes": len(archive_bytes), "zip_sha256": digest})
        report.update(status="passed", build_workers=sorted(build_workers), render_workers=sorted(render_workers),
                      scope="独立 Job 正常竞争和终态槽位释放；未覆盖 attempt 强杀/迟到上传/取消竞争或容量 SLA")
    except Exception:
        report["status"] = "failed"
        raise
    finally:
        drill.save("jobs.json", report)

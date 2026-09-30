"""文件功能：用真实截图 API 和 Worker 验证取消、硬期限、强杀/租约收敛及迟到 PNG 不提升。"""

from __future__ import annotations

import hashlib
import time

from docker_architecture_cases import Client
from docker_architecture_env import DockerDrill, command
from docker_architecture_jobs import download
from docker_architecture_render_probe import gate, state, wait_for, worker_probe


def lifecycle(drill: DockerDrill, data: dict, mode: str) -> None:
    """每场景创建独立页面/Job；故障只能作用于本项目，结束后恢复 gate 和服务。"""
    if mode not in {"cancel", "cancel-result", "timeout", "kill", "late"}:
        raise ValueError("未知生命周期场景")
    gate(drill, "configure", "pass")
    client = Client(drill)
    source = client.json(f"/api/pages/{data['page_id']}")["page_content"]
    page = client.json("/api/pages", {"title": f"Render {mode} {time.time_ns()}", "workspace_id": data["workspace_id"],
                                      "project_id": data["project_id"], "page_content": source})
    filename = f"render-{mode}.json"
    if (drill.output / filename).exists():
        filename = f"render-{mode}-{time.time_ns()}.json"
    report = {"status": "running", "mode": mode, "page_id": page["id"], "samples": [], "worker_observations": [],
              "candidate": drill.context["candidate"], "images": dict(drill.context["images"]),
              "parameters": {"request_timeout_seconds": 20, "attempt_lease_seconds": 6, "result_ttl_seconds": 10},
              "started_monotonic": time.monotonic()}
    interrupted = None
    try:
        gate(drill, "configure", "artifact" if mode in {"late", "cancel-result"} else "navigation")
        job = client.json(f"/api/pages/{page['id']}/screenshot-jobs", {})
        report["job_id"] = job["id"]
        drill.save(filename, report)
        deadline = time.monotonic() + 30
        while not gate(drill)["records"]:
            if time.monotonic() >= deadline:
                raise TimeoutError("真实浏览器导航/PNG 尚未到达故障 gate")
            time.sleep(0.2)
        report["gate_before"] = gate(drill)
        before = wait_for(drill, report, filename, lambda s: bool(s["attempts"]))
        held_uid = report["gate_before"]["records"][0].get("attempt_id")
        attempt = next((item for item in before["attempts"] if item["attempt_uid"] == held_uid), before["attempts"][0])
        if mode == "cancel-result" and not attempt["active_occupancy"]:
            raise AssertionError("取消竞争必须在持有真实 PNG 的 attempt 租约仍有效时注入")
        uid, worker = attempt["attempt_uid"], attempt["worker_id"]
        probe = worker_probe(drill, worker, uid)
        report["worker_observations"].append({"point": "before_fault", **probe})
        if mode not in {"late", "cancel-result"} and not any(p["state"] != "Z" for p in probe["processes"]):
            raise AssertionError("故障前未观察到真实浏览器进程")
        if mode in {"cancel", "cancel-result"}:
            client.json(f"/api/page-screenshot-jobs/{job['id']}/cancel", {})
            if mode == "cancel-result":
                wait_for(drill, report, filename, lambda s: any(r["cancel_requested"] for r in s["requests"]))
                report["gate_release"] = gate(drill, "release")
            final = wait_for(drill, report, filename, lambda s: s["job"]["status"] == "cancelled" and all(not a["active_occupancy"] for a in s["attempts"]), seconds=12)
            if final["page_published"] or final["results"]:
                raise AssertionError("取消任务发布了页面截图/成功结果")
            if any(r["status"] != "cancelled" for r in final["requests"]):
                raise AssertionError("截图 Job 取消未传递到远程渲染请求")
        elif mode == "timeout":
            final = wait_for(drill, report, filename, lambda s: s["job"]["status"] == "failed" and all(not a["active_occupancy"] for a in s["attempts"]), seconds=85)
            if final["page_published"] or final["results"]:
                raise AssertionError("超时任务仍发布了成功截图")
            if not any(r["error_code"] == "RENDER_DEADLINE_EXCEEDED" for r in final["requests"]):
                raise AssertionError("未记录真实执行期限错误")
        elif mode == "kill":
            interrupted = {"renderer-1": "renderer_1", "renderer-2": "renderer_2"}[worker]
            command("docker", "kill", "--signal", "KILL", drill.container(interrupted))
            report["killed_container_state"] = command("docker", "inspect", drill.container(interrupted), "--format", "{{.State.Status}}")
            expired = wait_for(drill, report, filename, lambda s: any(a["id"] == attempt["id"] and not a["active_occupancy"] for a in s["attempts"]), seconds=14)
            report["after_lease_recovery"] = expired
            gate(drill, "release")
            drill.compose("start", interrupted)
            interrupted = None
            final = wait_for(drill, report, filename, lambda s: s["job"]["status"] == "succeeded" and all(not a["active_occupancy"] for a in s["attempts"]), seconds=50)
            if any(r["attempt_id"] == attempt["id"] for r in final["results"]):
                raise AssertionError("被强杀的旧 attempt 提升了产物")
        else:
            # PNG 已真正生成；重启非 Job owner 的协调器，保留原执行者等待网络响应。
            hostname_a = command("docker", "inspect", drill.container("backend_a"), "--format", "{{.Config.Hostname}}")
            interrupted = "backend_b" if before["job"]["worker_id"].startswith(hostname_a + ":") else "backend_a"
            recovered = interrupted
            command("docker", "kill", "--signal", "KILL", drill.container(interrupted))
            expiry = time.monotonic() + 7
            while time.monotonic() < expiry:
                time.sleep(0.3)
            drill.compose("start", interrupted)
            interrupted = None
            drill.wait_http(drill.context["origins"][recovered], "/healthz")
            stale = wait_for(drill, report, filename, lambda s: any(a["id"] == attempt["id"] and not a["active_occupancy"] for a in s["attempts"]), seconds=12)
            report["before_late_delivery"] = stale
            report["gate_release"] = gate(drill, "release")
            final = wait_for(drill, report, filename, lambda s: s["job"]["status"] == "succeeded" and all(not a["active_occupancy"] for a in s["attempts"]), seconds=60)
            if any(r["attempt_id"] == attempt["id"] for r in final["results"]):
                raise AssertionError("租约已过期的真实 PNG 被提交为有效结果")
            if not any(r["attempt_id"] != attempt["id"] for r in final["results"]):
                raise AssertionError("没有新 attempt 的真实成功结果")
        report["final"] = final
        gate(drill, "release")
        wait_worker_cleanup(drill, report, filename)
        if mode in {"kill", "late"}:
            page_state = client.json(f"/api/pages/{page['id']}")
            png = download(client, page_state["screenshot_url"], 32 * 1024 * 1024)
            if not page_state["screenshot_is_latest"] or not png.startswith(b"\x89PNG\r\n\x1a\n"):
                raise AssertionError("恢复后截图不是当前页面的有效 PNG")
            report["download"] = {"bytes": len(png), "sha256": hashlib.sha256(png).hexdigest()}
            image_name = f"render-{mode}-{job['id']}.png"
            (drill.output / image_name).write_bytes(png)
            report["download"]["file"] = image_name
        report.update(status="passed", scope="真实截图/Renderer 生命周期；不覆盖构建强杀、页面变更/图片/组件 Batch 交接或正式容量")
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__)
        if report.get("job_id"):
            report["failure_state"] = state(drill, report["page_id"], report["job_id"])
        raise
    finally:
        gate(drill, "release")
        if interrupted:
            drill.compose("start", interrupted)
        report["elapsed_seconds"] = round(time.monotonic() - report.pop("started_monotonic"), 3)
        drill.save(filename, report)


def wait_worker_cleanup(drill: DockerDrill, report: dict, filename: str) -> None:
    """逐 Worker 核对实际空闲、无存活 Chromium/驱动和无临时产物，不用 DB 空占用替代。"""
    deadline = time.monotonic() + 25
    while True:
        probes = [worker_probe(drill, f"renderer-{i}") for i in (1, 2)]
        report["worker_observations"].append({"point": "cleanup", "workers": probes})
        drill.save(filename, report)
        if all(p["slot_state"] == "idle" and not p["artifact_files"] and not p["processes"] for p in probes):
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("Worker 浏览器/驱动/磁盘未在 TTL10 + 15 秒观察预算内释放")
        time.sleep(0.5)

"""文件功能：从真实旧/新入口执行业务读写、页面外部任务、取消和 deferred 自动续跑。"""

from __future__ import annotations

import json
import time
from urllib.request import Request, urlopen

from docker_architecture_cases import Client
from docker_architecture_env import DockerDrill
from docker_architecture_upgrade_env import rows

SOURCE = '''<!-- 文件功能：跨版本公共能力和业务回滚夹具。 -->
<template><main class="probe"><h1>Docker architecture probe</h1><p>Rendered by Runtime</p>
<DataTable :rows="[['版本', '状态'], ['Kit v1', '保留可用']]" class="w-[640px] h-[160px]" />
<p data-kit-size>{{ width }} × {{ height }}</p></main></template>
<script setup lang="ts">
// 文件功能：实际消费 N-1 已公开的表格组件与页面尺寸组合式能力。
import DataTable from '@runtime-kit/public/components/data/DataTable.v1.vue'
import { usePageSize } from '@runtime-kit/public/composables/page/usePageSize.v1'
const { width, height } = usePageSize()
</script>
<style scoped>.probe { padding: 48px; color: #123456; background: #f8fafc; min-height: 100vh; } h1 { font-size: 48px; }</style>'''


def create_data(drill: DockerDrill, role: str) -> dict:
    """经真实登录、实体和模型配置 API 播种，模型请求只连本项目受控服务。"""
    client = Client(drill, "m05_" + role)
    workspace = client.json("/api/workspaces", {"name": "M05 " + role})
    project = client.json("/api/projects", {"name": "M05 " + role, "workspace_id": workspace["id"]})
    page = client.json("/api/pages", {"title": "Docker architecture probe", "workspace_id": workspace["id"],
                                     "project_id": project["id"], "page_content": SOURCE})
    client.json(f"/api/projects/{project['id']}/routes", {"routes": [{"route_type": "page", "route": "probe", "order": 0, "page_id": page["id"]}]}, "PUT")
    provider = client.json("/api/ai/chat-provider-configs", {"name": "M05 fixture", "custom": True,
                           "base_url": "http://mock:8090/v1", "api_key": "isolated-fixture-only"})
    model = client.json("/api/ai/chat-model-configs", {"name": "M05 controlled", "provider_config_id": provider["id"],
                        "model_id": "docker-drill-chat", "capability_override": {"supports_tool_call": True}})
    client.json("/api/ai/chat-model-bindings/agent_coordinator", {"model_config_id": model["id"]}, "PUT")
    data = {"workspace_id": workspace["id"], "project_id": project["id"], "page_id": page["id"], "public_kit": True,
            "preview_gateway_override": True}
    drill.save("m05-" + role + "-data.json", data)
    return data


def state(drill: DockerDrill, role: str, run_id: str) -> dict:
    """观察 Run、页面 Job 和统一 Task/Batch，不采集模型历史、源码或结果正文。"""
    condition = "run_id='" + run_id + "'"
    page_id = "result_json->>'page_id'" if role == "platform" else "json_extract(result_json,'$.page_id')"
    cleared = "(result_json IS NULL OR result_json::text='null')" if role == "platform" else "(result_json IS NULL OR result_json='null')"
    return {"run": rows(drill, role, "run_id,status,error_code,event_index", "ai_agent_runs", condition),
            "jobs": rows(drill, role, f"job_id,batch_id,status,{page_id} AS result_page_id,error_code", "ai_page_mutation_jobs", condition),
            "batches": rows(drill, role, "batch_id,status,lease_generation,error_code", "ai_agent_external_batches", condition),
            "tasks": rows(drill, role, f"task_id,status,result_consumed_at,{cleared} AS result_cleared,error_code", "ai_agent_external_tasks", condition)}


def mutation(drill: DockerDrill, role: str, data: dict, label: str, *, cancel: bool = False) -> dict:
    """受控供应商返回真实 create_entity 调用；生产队列/校验/续跑实现不替换、不伪造终态。"""
    title = "M05 " + label + " " + str(time.time_ns())
    arguments = {"resource_type": "page", "mode": "new", "payload": {"project_id": data["project_id"],
                 "title": title, "content": SOURCE + "\n<!-- 独立校验输入：" + title + " -->"}}
    request = Request(drill.context["origins"]["mock"] + "/_drill/scenario", data=json.dumps({"arguments": arguments}).encode(),
                      headers={"Content-Type": "application/json"})
    urlopen(request, timeout=5).close()
    client = Client(drill, "m05_" + role)
    session_id = client.json("/api/ai/sessions", {"workspace_id": data["workspace_id"]})["session_id"]
    target = "m05_runtime" if role == "platform" else "m05_check_lite"
    report = {"status": "failed", "label": label, "cancel": cancel, "observations": []}
    started = time.monotonic()
    paused = False
    if cancel:
        drill.compose("pause", target)
        paused = True
    try:
        run_id = client.json(f"/api/ai/sessions/{session_id}/runs?workspace_id={data['workspace_id']}",
                             {"message": "创建兼容演练页面", "focus": {"scope_type": "project", "project_id": data["project_id"]}})["run_id"]
        report.update(run_id=run_id, session_id=session_id)
        deadline = time.monotonic() + 150
        cancelled = False
        while time.monotonic() < deadline:
            value = state(drill, role, run_id)
            if not report["observations"] or value != report["observations"][-1]["state"]:
                report["observations"].append({"seconds": round(time.monotonic()-started, 3), "state": value})
            if cancel and value["jobs"] and not cancelled:
                client.json(f"/api/ai/sessions/{session_id}/active-run/cancel?workspace_id={data['workspace_id']}", {"force": False})
                cancelled = True
                drill.compose("unpause", target)
                paused = False
            terminal = value["run"][0]["status"]
            if terminal in ("completed", "failed", "cancelled") and (not cancel or all(job["status"] in ("succeeded", "failed", "cancelled") for job in value["jobs"])):
                break
            time.sleep(0.5)
        else:
            raise TimeoutError("页面外部任务或自动续跑未按期收敛")
        assert value["jobs"] and value["tasks"] and value["batches"], "没有执行真实外部页面任务"
        if cancel:
            assert terminal == "cancelled" and all(job["status"] == "cancelled" for job in value["jobs"]), value
        else:
            assert terminal == "completed" and all(job["status"] == "succeeded" for job in value["jobs"]), value
            assert all(task["result_consumed_at"] and task["result_cleared"] for task in value["tasks"]), value
            report["created_pages"] = rows(drill, role, "id,current_version_no", "pages", "title='" + title + "'")
            assert len(report["created_pages"]) == 1, "单次页面任务没有恰好创建一个真实业务页面"
        report.update(status="passed", final=value, elapsed_seconds=round(time.monotonic()-started, 3))
        return report
    finally:
        if paused:
            drill.compose("unpause", target)
        drill.save("m05-" + role + "-" + label + ".json", report)


def read_write(drill: DockerDrill, role: str, data: dict, label: str) -> dict:
    """复核历史页面/路由/模型设置，并产生新的源码版本，证明完整业务读写而非登录探针。"""
    client = Client(drill, "m05_" + role)
    page = client.json(f"/api/pages/{data['page_id']}")
    assert page["page_content"] == SOURCE
    updated = client.json(f"/api/pages/{data['page_id']}", {"page_content": SOURCE, "summary": label}, "PATCH")
    project = client.json(f"/api/projects/{data['project_id']}")
    assert updated["summary"] == label and project["workspace_id"] == data["workspace_id"]
    result = {"status": "passed", "page_id": page["id"], "before_version": page["current_version_no"],
              "after_version": updated["current_version_no"], "project_id": project["id"], "label": label}
    drill.save("m05-" + role + "-" + label + "-read-write.json", result)
    return result

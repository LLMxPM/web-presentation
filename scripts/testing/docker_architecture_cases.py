"""文件功能：通过隔离环境的真实 API 验证普通 Run 强杀、会话解除与页面产物链路。"""

from __future__ import annotations

import json
import time
from http.cookiejar import CookieJar
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from docker_architecture_env import DockerDrill, command


class Client:
    """只绑定上下文中的回环端口，登录 Cookie 不写入报告。"""

    def __init__(self, drill: DockerDrill, role: str = "gateway") -> None:
        """创建独立 Cookie 会话，便于明确指定执行副本。"""
        self.origin = drill.context["origins"][role]
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))
        self.json("/api/auth/login", {"username": "admin", "password": drill.context["password"]})

    def json(self, path: str, payload: dict | None = None, method: str | None = None):
        """通过有界 HTTP 请求读写测试实体，不允许调用其它 origin。"""
        request = Request(self.origin + path, data=json.dumps(payload).encode() if payload is not None else None,
                          headers={"Content-Type": "application/json"}, method=method)
        with self.opener.open(request, timeout=120) as response:
            data = response.read(4 * 1024 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024:
            raise ValueError("测试 API 响应超过上限")
        return json.loads(data)


def sql(drill: DockerDrill, query: str):
    """仅在演练 PG 中查询脱敏字段；所有场景写入通过 API 或明确标注的 fixture。"""
    text = command("docker", "exec", drill.container("postgres"), "psql", "-U", "drill", "-d", "architecture_e2e", "-tAc", query)
    return json.loads(text) if text else None


def seed(drill: DockerDrill) -> dict:
    """用正常登录、实体及模型配置 API 创建数据，模型连接仅指向本地 fixture。"""
    client = Client(drill)
    workspace = client.json("/api/workspaces", {"name": "Docker architecture drill"})
    project = client.json("/api/projects", {"name": "Docker architecture drill", "workspace_id": workspace["id"]})
    source = """<!-- 文件功能：提供架构演练页面，覆盖 Vue、scoped CSS 与预览版本传播。 -->
<template><main class="probe"><h1>Docker architecture probe</h1><p>{{ message }}</p></main></template>
<script setup lang="ts">
// 文件功能：提供架构演练页面，覆盖 Vue、scoped CSS 与预览版本传播。
import { ref } from 'vue'
const message = ref('Rendered by Runtime')
</script>
<style scoped>.probe { padding: 48px; color: #123456; background: #f8fafc; min-height: 100vh; } h1 { font-size: 48px; }</style>"""
    page = client.json("/api/pages", {"title": "Docker architecture probe", "workspace_id": workspace["id"], "project_id": project["id"], "page_content": source})
    client.json(f"/api/projects/{project['id']}/routes", {"routes": [{"route_type": "page", "route": "probe", "order": 0, "page_id": page["id"]}]}, "PUT")
    provider = client.json("/api/ai/chat-provider-configs", {"name": "Docker local fixture", "custom": True, "base_url": "http://mock:8090/v1", "api_key": "isolated-fixture-only"})
    model = client.json("/api/ai/chat-model-configs", {"name": "Docker controlled stream", "provider_config_id": provider["id"], "model_id": "docker-drill-chat", "capability_override": {"supports_tool_call": True}})
    client.json("/api/ai/chat-model-bindings/agent_coordinator", {"model_config_id": model["id"]}, "PUT")
    result = {"workspace_id": workspace["id"], "project_id": project["id"], "page_id": page["id"], "model_id": model["id"]}
    drill.save("seed.json", result)
    return result


def run_state(drill: DockerDrill, run_id: str) -> dict:
    """读取持久化 Run 与事件计数，不包含消息、模型历史和工具参数。"""
    if not all(char.isalnum() or char in "-_" for char in run_id):
        raise ValueError("非法测试 Run ID")
    return sql(drill, f"SELECT row_to_json(t) FROM (SELECT run_id,status,process_owner,error_code,started_at,finished_at,event_index,(SELECT count(*) FROM ai_agent_run_events e WHERE e.run_id=r.run_id AND e.event IN ('run.error','run.completed','run.cancelled')) AS terminal_events FROM ai_agent_runs r WHERE run_id='{run_id}') t")


def start_run(client: Client, data: dict, session_id: str | None = None) -> tuple[str, str]:
    """明确从指定副本启动真实后台 Run，不订阅 SSE。"""
    if session_id is None:
        session_id = client.json("/api/ai/sessions", {"workspace_id": data["workspace_id"]})["session_id"]
    result = client.json(f"/api/ai/sessions/{session_id}/runs?workspace_id={data['workspace_id']}",
                         {"message": "本地容器强杀与心跳演练", "focus": {"scope_type": "workspace"}})
    return session_id, result["run_id"]


def wait_state(drill: DockerDrill, run_id: str, expected: str, seconds: int = 25) -> dict:
    """在明确期限内轮询数据库终态，异常状态立即作为失败保留。"""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        state = run_state(drill, run_id)
        if state and state["status"] == expected:
            return state
        if state and state["status"] in ("failed", "cancelled", "completed"):
            raise AssertionError(f"Run 意外终态：{state}")
        time.sleep(0.25)
    raise TimeoutError(f"Run 未达到 {expected}：{run_state(drill, run_id)}")


def owner_drill(drill: DockerDrill, data: dict, *, mode: str = "kill") -> dict:
    """强杀 A 后从同 hostname/PID=1 重启，验证 UUID 隔离及 B 无输出期间继续存活。"""
    origin = drill.context["origins"]["mock"]
    urlopen(origin + "/reset", timeout=5).close()
    a, b = Client(drill, "backend_a"), Client(drill, "backend_b")
    session_a, run_a = start_run(a, data)
    _session_b, run_b = start_run(b, data)
    wait_state(drill, run_a, "running")
    wait_state(drill, run_b, "running")
    deadline = time.monotonic() + 20
    while json.load(urlopen(origin + "/status", timeout=5))["arrivals"] < 2:
        if time.monotonic() >= deadline:
            raise TimeoutError("真实模型请求未到达本地流服务")
        time.sleep(0.25)
    before = {"a": run_state(drill, run_a), "b": run_state(drill, run_b)}
    killed_at = time.monotonic()
    if mode == "pause":
        command("docker", "pause", drill.container("backend_a"))
    else:
        command("docker", "kill", "--signal", "KILL", drill.container("backend_a"))
        if mode == "hostname":
            path = drill.directory / "compose.json"
            config = json.loads(path.read_text(encoding="utf-8"))
            config["services"]["backend_a"]["hostname"] = "rebuilt-a-" + str(int(time.time()))
            path.write_text(json.dumps(config, indent=2), encoding="utf-8")
            drill.compose("up", "-d", "--force-recreate", "backend_a")
        else:
            drill.compose("start", "backend_a")
        drill.wait_http(drill.context["origins"]["backend_a"], "/healthz")
    failed = wait_state(drill, run_a, "failed", seconds=18)
    elapsed = time.monotonic() - killed_at
    assert failed["error_code"] == "AI_RUN_PROCESS_STOPPED", failed
    assert failed["terminal_events"] == 1, "双收敛者产生重复终态事件"
    assert elapsed <= 16, f"TTL12 + sweep1 + 事务容差3 预算超时：{elapsed}"
    protected = run_state(drill, run_b)
    assert protected["status"] == "running" and protected["process_owner"] == before["b"]["process_owner"], protected
    assert protected["event_index"] == before["b"]["event_index"], "B 在观察窗产生模型事件，未覆盖静默保护"
    pause_observation = None
    if mode == "pause":
        urlopen(origin + "/release", timeout=5).close()
        command("docker", "unpause", drill.container("backend_a"))
        wait_state(drill, run_b, "completed")
        time.sleep(2)
        late = run_state(drill, run_a)
        assert late["event_index"] == failed["event_index"] and late["terminal_events"] == 1, "暂停旧实例恢复后提交了迟到结果"
        pause_observation = {"after_unpause": late, "scope": "进程恢复后收到了模型响应，但失效写围栏阻止迟到提交"}
        drill.compose("restart", "backend_a")
        drill.wait_http(drill.context["origins"]["backend_a"], "/healthz")
        urlopen(origin + "/reset", timeout=5).close()
    # 同一容器 hostname 与 PID=1 保持相同，进程 UUID 必须变化。
    _session_again, run_again = start_run(Client(drill, "backend_a"), data, session_a)
    restarted = wait_state(drill, run_again, "running")
    old_owner, new_owner = before["a"]["process_owner"], restarted["process_owner"]
    if mode == "hostname":
        assert old_owner.split(":")[0] != new_owner.split(":")[0], "未真正改变 hostname"
        assert old_owner.split(":")[-2] == new_owner.split(":")[-2] == "1", "未覆盖容器 PID 重用"
    else:
        assert old_owner.rsplit(":", 1)[0] == new_owner.rsplit(":", 1)[0], (old_owner, new_owner)
    assert old_owner != new_owner, "PID 重用时实例 UUID 未更新"
    urlopen(origin + "/release", timeout=5).close()
    completed_b = wait_state(drill, run_b, "completed")
    completed_again = wait_state(drill, run_again, "completed")
    events = sql(drill, f"SELECT coalesce(json_agg(t),'[]'::json) FROM (SELECT event,count(*) AS count FROM ai_agent_run_events WHERE run_id='{run_a}' GROUP BY event ORDER BY event) t")
    final = run_state(drill, run_a)
    assert final["status"] == "failed" and final["event_index"] == failed["event_index"], "旧 Run 产生了迟到写入"
    result = {"status": "passed", "mode": mode, "parameters": {"ttl_seconds": 12, "heartbeat_seconds": 2, "sweep_seconds": 1, "observation_budget_seconds": 16},
              "kill_to_terminal_seconds": round(elapsed, 3), "before": before, "after_kill": failed, "quiet_b": protected,
              "restarted_run": completed_again, "completed_b": completed_b, "old_run_events": events, "pause_observation": pause_observation,
              "scope": "真实 API/执行器、无 SSE、重启身份隔离；未覆盖全部外部 Batch 保护矩阵"}
    drill.save("owner" + ("-" + mode if mode != "kill" else "") + ".json", result)
    return result

"""文件功能：采集演练截图 Job、远程 attempt、实际 Chromium PID 与临时产物的脱敏证据。"""

from __future__ import annotations

import json
import time
from urllib.request import Request, urlopen

from docker_architecture_cases import sql
from docker_architecture_env import DockerDrill, command


def gate(drill: DockerDrill, action: str = "status", mode: str | None = None) -> dict:
    """仅控制本演练回环代理；故障阶段必须显式通过 setup 开启。"""
    if not drill.context.get("fault_injection"):
        raise ValueError("故障场景需要 setup --fault-injection")
    data = None if action == "status" else json.dumps({"mode": mode} if mode else {}).encode()
    request = Request(drill.context["origins"]["gate"] + "/_drill/" + action,
                      data=data, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        return json.load(response)


def state(drill: DockerDrill, page_id: int, job_id: int) -> dict:
    """按本轮整数主键查询状态、结果身份和额度，不读取源码、快照票据或密钥。"""
    page_id, job_id = int(page_id), int(job_id)
    query = f"""SELECT json_build_object(
      'job',(SELECT row_to_json(j) FROM (SELECT id,status,attempt_count,error_code,cancel_requested_at,worker_id,lease_expires_at,finished_at FROM page_screenshot_jobs WHERE id={job_id}) j),
      'requests',(SELECT coalesce(json_agg(r),'[]'::json) FROM (SELECT id,status,attempt_count,cancel_requested,result_id,error_code,deadline_at,finished_at FROM render_requests WHERE page_id={page_id} AND business_stage='page.screenshot' ORDER BY id) r),
      'attempts',(SELECT coalesce(json_agg(a),'[]'::json) FROM (SELECT a.id,a.request_id,a.attempt_uid,a.attempt_no,a.worker_id,a.worker_epoch,a.status,a.active_occupancy,a.cleanup_status,a.error_code,a.lease_expires_at,a.finished_at FROM render_attempts a JOIN render_requests r ON r.id=a.request_id WHERE r.page_id={page_id} AND r.business_stage='page.screenshot' ORDER BY a.id) a),
      'results',(SELECT coalesce(json_agg(x),'[]'::json) FROM (SELECT x.id,x.request_id,x.attempt_id FROM render_results x JOIN render_requests r ON r.id=x.request_id WHERE r.page_id={page_id} ORDER BY x.id) x),
      'active_total',(SELECT count(*) FROM render_attempts WHERE active_occupancy=1),
      'page_published',(SELECT screenshot_storage_key IS NOT NULL FROM pages WHERE id={page_id}))"""
    return sql(drill, query)


def worker_probe(drill: DockerDrill, worker: str, attempt_uid: str | None = None) -> dict:
    """在对应 Worker 内读取 /proc 与真实控制 API，服务 token 不离开该进程。"""
    service = {"renderer-1": "renderer_1", "renderer-2": "renderer_2"}[worker]
    script = """
import json
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from wp_renderer.config import get_renderer_settings
from render_contracts.tokens import issue_worker_credential
settings=get_renderer_settings()
headers={'x-render-service-token':issue_worker_credential(secret=settings.credential_secret,worker_id='backend:'+settings.render_worker_id)}
def get(path):
    try:
        with urlopen(Request('http://127.0.0.1:7400'+path,headers=headers),timeout=3) as r:
            return json.load(r)
    except HTTPError as e:
        return {'http_status':e.code}
caps=get('/internal/render/v1/capabilities')
uid=__import__('sys').argv[1]
receipt=get('/internal/render/v1/executions/'+uid) if uid else {}
processes=[]
for p in Path('/proc').iterdir():
    if not p.name.isdigit(): continue
    try:
        name=(p/'comm').read_text().strip()
        try: executable=(p/'exe').readlink().name
        except OSError: executable=''
        if any(v in (name+' '+executable).lower() for v in ('chrome','chromium','playwright','node')):
            raw=(p/'stat').read_text().rsplit(')',1)[1].split()
            processes.append({'pid':int(p.name),'name':name,'executable':executable,'state':raw[0],'ppid':int(raw[1])})
    except (OSError,IndexError): pass
files=[p for p in settings.workspace_path.rglob('*') if p.is_file()]
print(json.dumps({'worker_id':caps.get('worker_id'),'worker_epoch':caps.get('worker_epoch'),'slot_state':caps.get('slot_state'),
 'init_process':{'name':Path('/proc/1/comm').read_text().strip(),'executable':Path('/proc/1/exe').readlink().name},
 'receipt':{k:receipt.get(k) for k in ('http_status','status','resource_state','cleaned_at','finished_at')},
 'error_code':(receipt.get('error') or {}).get('code'),'processes':processes,
 'artifact_files':len(files),'artifact_bytes':sum(p.stat().st_size for p in files)}))
"""
    return json.loads(command("docker", "exec", drill.container(service), "python", "-c", script, attempt_uid or ""))


def wait_for(drill: DockerDrill, report: dict, filename: str, predicate, *, seconds: float = 35) -> dict:
    """保存每轮状态直至明确断言成立；保留失败前完整时间轴，未知量不填零。"""
    deadline = time.monotonic() + seconds
    while True:
        snapshot = state(drill, report["page_id"], report["job_id"])
        snapshot["elapsed_seconds"] = round(time.monotonic() - report["started_monotonic"], 3)
        report["samples"].append(snapshot)
        drill.save(filename, report)
        if snapshot["active_total"] > 2:
            raise AssertionError("双协调器突破演练全局额度 2")
        if predicate(snapshot):
            return snapshot
        if time.monotonic() >= deadline:
            raise TimeoutError("渲染生命周期条件超时，见场景原始报告")
        time.sleep(0.3)

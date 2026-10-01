"""文件功能：验证真实 N/N-1 Runtime/Renderer、公开 Kit、截图 ZIP 与旧产物加载组合。"""

from __future__ import annotations

import hashlib
import json
import time
from copy import deepcopy
from urllib.error import HTTPError

from docker_architecture_cases import Client, sql
from docker_architecture_env import ROOT, DockerDrill, command
from docker_architecture_old_entries import old_entries
from docker_architecture_pipeline import pipeline, update_runtime
from docker_architecture_render_probe import worker_probe
from docker_architecture_unsupported import unsupported_pipeline
from docker_architecture_upgrade_business import SOURCE
from docker_architecture_upgrade_env import rows


def browser_pipeline(drill: DockerDrill, data: dict, label: str, *, origin: str | None = None, preview: bool = True, reuse: bool = False) -> dict:
    """从目标真实 Gateway 下载 PNG/ZIP，再打开预览和 ZIP；临时切换仅用于现有浏览器探针上下文。"""
    saved_path = drill.output / (label + "-pipeline.json")
    if reuse and origin is None and saved_path.exists():
        saved = json.loads(saved_path.read_text(encoding="utf-8"))
        version = Client(drill).json(f"/api/pages/{data['page_id']}")["current_version_no"]
        artifact = drill.output / saved["artifact_directory"] / "build.zip"
        if (saved["status"] == "passed" and saved.get("images") == actual_images(drill, origin)
                and saved["screenshot"]["page_version"] == version and artifact.exists()
                and hashlib.sha256(artifact.read_bytes()).hexdigest() == saved["build"]["sha256"]):
            return {**saved, "reused_evidence": label + "-pipeline.json"}
    original_context = deepcopy(drill.context)
    seed_path = drill.output / "seed.json"
    original_seed = seed_path.read_bytes()
    try:
        if origin:
            drill.context["origins"]["gateway"] = origin
            data = {**data, "probe_service": "m05_platform_migrate" if origin == drill.context["origins"]["m05_platform"] else "m05_lite_migrate"}
        (drill.directory / "context.json").write_text(json.dumps(drill.context, indent=2), encoding="utf-8")
        seed_path.write_text(json.dumps(data), encoding="utf-8")
        if preview:
            command("node", str(ROOT / "scripts/testing/docker-architecture-browser.mjs"), str(drill.directory), "single", timeout=90)
            drill.save(label + "-preview.json", json.loads((drill.output / "browser-single.json").read_text(encoding="utf-8")))
        pipeline(drill, data)
        command("node", str(ROOT / "scripts/testing/docker-architecture-browser.mjs"), str(drill.directory), "build", timeout=90)
        latest = json.loads((drill.output / "pipeline-current.json").read_text(encoding="utf-8"))
        report = json.loads((drill.output / latest["directory"] / "pipeline.json").read_text(encoding="utf-8"))
        report.update(artifact_directory=latest["directory"], build_site=latest["build_site"])
        report["images"] = actual_images(drill, origin)
        drill.save(label + "-pipeline.json", report)
        drill.save(label + "-browser-build.json", json.loads((drill.output / "browser-build.json").read_text(encoding="utf-8")))
        return report
    finally:
        seed_path.write_bytes(original_seed)
        drill.context = original_context
        (drill.directory / "context.json").write_text(json.dumps(drill.context, indent=2), encoding="utf-8")


def actual_images(drill: DockerDrill, origin: str | None) -> dict:
    """绑定实际运行容器，旧入口或嵌入 Runtime 不得误记成主控制面的 N 镜像。"""
    backend = "backend_a" if not origin else "m05_platform" if origin == drill.context["origins"]["m05_platform"] else "m05_lite"
    runtime = "preview_a" if not origin else "m05_runtime" if backend == "m05_platform" else "m05_lite"
    return {name: command("docker", "inspect", drill.container(service), "--format", "{{.Image}}")
            for name, service in (("backend", backend), ("runtime", runtime), ("renderer", "renderer_1"))}


def renderer_image(drill: DockerDrill, image: str) -> str:
    """只在空闲 Worker 窗口替换专属 Renderer，保持服务身份与单槽预算。"""
    count = sql(drill, "SELECT count(*) FROM render_attempts WHERE active_occupancy=1")
    assert count == 0, "仍有执行中 attempt，禁止替换 Worker"
    for role in ("platform", "lite"):
        assert rows(drill, role, "count(*) AS total", "render_attempts", "active_occupancy=1")[0]["total"] == 0, "M05 库仍占用 Worker"
    image_id = command("docker", "image", "inspect", image, "--format", "{{.Id}}")
    drill.save("m05-before-renderer-replace-" + str(time.time_ns()) + ".json", {
        "target_image": image_id, "observations": [worker_probe(drill, f"renderer-{i}") for i in (1, 2)],
    })
    path = drill.directory / "compose.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    for index in (1, 2):
        config["services"][f"renderer_{index}"]["image"] = image_id
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    drill.compose("up", "-d", "--no-deps", "--force-recreate", "renderer_1", "renderer_2")
    return image_id


def rejected_preview(drill: DockerDrill, data: dict, label: str) -> dict:
    """验证旧 Runtime 没有发布身份时，新 Backend 的正常 iframe 入口明确拒绝。"""
    client = Client(drill)
    page = client.json(f"/api/pages/{data['page_id']}")
    try:
        preview = client.json(f"/api/pages/{data['page_id']}/versions/{page['current_version_no']}/preview-artifact", {})
        # artifact 创建可成功，拒绝发生在真正浏览器入口绑定 Runtime 身份时。
        with client.opener.open(preview["preview_url"], timeout=20):
            raise AssertionError("旧 Runtime 无身份却被静默接受")
    except HTTPError as exc:
        value = json.loads(exc.read())
        assert exc.code == 503 and value.get("code") == "RUNTIME_VERSION_UNKNOWN", value
        report = {"status": "passed", "behavior": "rejected", "http_status": exc.code, "code": value["code"]}
        drill.save(label + "-preview.json", report)
        return report


def protocol_rejection(drill: DockerDrill, label: str, *, legacy: bool = False) -> dict:
    """向实际 Worker 发送除版本外有效的请求，协议拒绝不得接管或改变槽位代次。"""
    code = """import json
from datetime import UTC,datetime,timedelta
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from wp_renderer.config import get_renderer_settings
from render_contracts.schema import ExecutionRequest,SnapshotRef,ViewportSpec
from render_contracts.tokens import AdmissionTicket,PreviewAccess,issue_worker_credential
s=get_renderer_settings(); h={'x-render-service-token':issue_worker_credential(secret=s.credential_secret,worker_id='backend:'+s.render_worker_id),'Content-Type':'application/json'}
def get():
 return json.load(urlopen(Request('http://127.0.0.1:7400/internal/render/v1/capabilities',headers=h)))
c=get(); n=datetime.now(UTC); stop=n+timedelta(seconds=30); digest='a'*64
r=ExecutionRequest(contract_version='internal/render/v1',operation='page.capture',request_id='m05-version-negative',attempt_id='m05-version-negative',request_digest=digest,workspace_id=1,trace_id='m05',snapshot_ref=SnapshotRef(artifact_id='m05',input_digest=digest),input_digest=digest,render_profile_digest=c['render_profile_digest'],viewport=ViewportSpec(width=1920,height=1080),operation_options={},deadline_at=stop.isoformat(),remaining_budget_ms=30000,admission_ticket=AdmissionTicket.issue(secret=s.credential_secret,request_digest=digest,workspace_id=1,worker_id=c['worker_id'],worker_epoch=c['worker_epoch'],slot_generation=c['slot_generation']+1,accept_before=n+timedelta(seconds=10),stop_by=stop,attempt_id='m05-version-negative'),preview_access=PreviewAccess(navigation_base_url='http://m05_lite/runtime/__preview',preview_token='unconsumed-negative',artifact_id='m05',expires_at=stop.isoformat(),runtime_protocol_version='render-ready.v1')).to_dict()
r['contract_version']='internal/render/v999'
try:
 urlopen(Request('http://127.0.0.1:7400/internal/render/v1/executions',data=json.dumps(r).encode(),headers=h))
 raise AssertionError('协议破坏性版本未拒绝')
except HTTPError as e:
 raw=e.read(); legacy=LEGACY; expected=500 if legacy else 400
 assert e.code==expected, {'http_status':e.code,'body_bytes':len(raw),'body_type':e.headers.get('Content-Type')}
 code=None if legacy else json.loads(raw)['detail']['code']; assert legacy or code=='RENDER_CONTRACT_MISMATCH'
after=get(); assert after['slot_state']=='idle' and after['slot_generation']==c['slot_generation']
print(json.dumps({'status':'observed_legacy_limitation' if legacy else 'passed','http_status':expected,'code':code,'protocol_version':c['protocol_version'],'slot_generation_unchanged':True}))
"""
    code = code.replace("LEGACY", repr(legacy))
    report = json.loads(command("docker", "exec", drill.container("renderer_1"), "python", "-c", code))
    drill.save(label + "-protocol-negative.json", report)
    return report


def combinations(drill: DockerDrill) -> None:
    """全 N、N Runtime+旧 Renderer、旧 Runtime 缺身份拒绝及旧完整入口逐项留证。"""
    data = json.loads((drill.output / "seed.json").read_text(encoding="utf-8"))
    client = Client(drill)
    if client.json(f"/api/pages/{data['page_id']}")["page_content"] != SOURCE:
        client.json(f"/api/pages/{data['page_id']}", {"page_content": SOURCE}, "PATCH")
    data["public_kit"] = True
    original_renderer = drill.context["images"]["renderer"]
    original_runtime = drill.context["images"]["runtime"]
    report = {"status": "running", "source_n1": "4c7eee8", "combinations": []}
    try:
        report["combinations"].append({"backend": "N", "runtime": "N", "renderer": "N", "result": browser_pipeline(drill, data, "m05-all-n", reuse=True)})
        drill.save("m05-combinations.json", report)
        protocol_rejection(drill, "m05-renderer-n")
        old_renderer = renderer_image(drill, "wp-renderer-m05-4c7eee8:local")
        report["renderer_n1_image"] = old_renderer
        protocol_rejection(drill, "m05-renderer-n1", legacy=True)
        report["combinations"].append({"backend": "N", "runtime": "N", "renderer": "N-1", "result": browser_pipeline(drill, data, "m05-old-renderer", reuse=True)})
        drill.save("m05-combinations.json", report)
        update_runtime(drill, "wp-runtime-m05-4c7eee8:local")
        report["combinations"].append({"backend": "N", "runtime": "N-1", "renderer": "N-1",
                "preview": rejected_preview(drill, data, "m05-old-runtime-renderer"),
                "result": unsupported_pipeline(drill, data, "m05-old-runtime-renderer")})
        drill.save("m05-combinations.json", report)
        renderer_image(drill, original_renderer)
        report["combinations"].append({"backend": "N", "runtime": "N-1", "renderer": "N",
                "preview": rejected_preview(drill, data, "m05-old-runtime"),
                "result": unsupported_pipeline(drill, data, "m05-old-runtime")})
        drill.save("m05-combinations.json", report)
        report["combinations"].extend(old_entries(drill, runtime_n=original_runtime))
        report["status"] = "passed"
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        renderer_image(drill, original_renderer)
        update_runtime(drill, original_runtime)
        drill.save("m05-combinations.json", report)

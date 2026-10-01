"""文件功能：核对镜像内真实源码与公开 Kit 指纹，并在摘除前检查本次各数据库的 Worker 占用。"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

from docker_architecture_env import ROOT, DockerDrill, command


def source_check(image: str, source: Path, folders: tuple[str, ...], destination: str) -> dict:
    """独立容器无网络读取源码；统一换行后逐文件比较，避免把继承的 OCI revision 当应用来源。"""
    files = [path.relative_to(source).as_posix() for folder in folders for path in (source / folder).rglob("*.py")]
    expected = {name: hashlib.sha256((source / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() for name in files}
    code = "import sys,json,hashlib; from pathlib import Path; names=json.load(sys.stdin); print(json.dumps({name:hashlib.sha256((Path(" + repr(destination) + ")/name).read_bytes().replace(b'\\r\\n',b'\\n')).hexdigest() for name in names}))"
    result = subprocess.run(["docker", "run", "-i", "--rm", "--network", "none", "--entrypoint", "python", image, "-c", code],
                            input=json.dumps(files), capture_output=True, text=True, encoding="utf-8", timeout=90, check=True)
    actual = json.loads(result.stdout)
    assert actual == expected, "镜像源码与记录的候选不一致"
    digest = hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()
    return {"status": "passed", "files": len(files), "normalized_sources_sha256": digest, "image_id": image}


def kit(image: str) -> dict:
    """从真实生产依赖裁剪后的 Runtime 读取清单与全部公开入口，记录每个保留版本的源码摘要。"""
    code = """const fs=require('fs'),path=require('path'),crypto=require('crypto');
const manifest=JSON.parse(fs.readFileSync('src/runtime-kit/manifest/runtime-kit.manifest.json','utf8'));
const exports=manifest.exports.map(item=>{ let file=item.import_path.replace('@runtime-kit','src/runtime-kit'); if(!fs.existsSync(file))file+='.ts';return {name:item.name,import_path:item.import_path,sha256:crypto.createHash('sha256').update(fs.readFileSync(file,'utf8').replace(/\\r\\n/g,'\\n')).digest('hex')}});
console.log(JSON.stringify({version:manifest.version,exports,build_id:fs.existsSync('.runtime-build-id')?fs.readFileSync('.runtime-build-id','utf8').trim():null}));"""
    return json.loads(command("docker", "run", "--rm", "--network", "none", "--entrypoint", "node", image, "-e", code))


def provenance(drill: DockerDrill) -> None:
    """分别绑定完整旧 Git 源与当前补丁候选，保留依赖锁、镜像身份及全部旧公开入口比较。"""
    old = ROOT / ".tmp/docker-architecture-images/4c7eee8"
    images = drill.context["m05_images"]
    current = drill.context["images"]
    records = {"candidate": command("git", "rev-parse", "HEAD"), "n1_ref": command("git", "rev-parse", "4c7eee8"),
               "locks": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in ("uv.lock", "pnpm-lock.yaml")},
               "source_checks": {}}
    for label, image, root, folders in (
        ("backend_n", current["backend"], ROOT, ("backend/app", "backend/migrations")),
        ("platform_n", images["platform_n"], ROOT, ("backend/app", "backend/migrations")),
        ("backend_n1", images["lite"], old, ("backend/app", "backend/migrations")),
        ("platform_n1", images["platform"], old, ("backend/app", "backend/migrations")),
        ("renderer_n", current["renderer"], ROOT, ("renderer/wp_renderer", "packages/render-contracts/src/render_contracts")),
        ("renderer_n1", command("docker", "image", "inspect", "wp-renderer-m05-4c7eee8:local", "--format", "{{.Id}}"), old,
         ("renderer/wp_renderer", "packages/render-contracts/src/render_contracts")),
    ):
        records["source_checks"][label] = source_check(image, root, folders, "/app")
    old_kit, new_kit = kit(images["runtime"]), kit(current["runtime"])
    assert old_kit["version"] == new_kit["version"] == "1.0.0"
    assert old_kit["exports"] == new_kit["exports"], "旧公开路径或实现发生漂移，不能宣称保留兼容"
    records["kit"] = {"status": "passed", "n1": old_kit, "n": new_kit,
                      "rendered_sample": ["DataTable.v1", "usePageSize.v1"], "scope": "全部公开入口存在/源码一致，实际渲染样本为表格与尺寸能力"}
    drill.save("m05-provenance.json", records)


def removal_gate(drill: DockerDrill) -> None:
    """对共享 Worker 涉及的三个本次专属库执行只读 CLI；拒绝在占用未释放时摘除/清理。"""
    reports = []
    for database, service in (("architecture_e2e", "backend_a"), ("m05_pg", "m05_platform_migrate"), ("m05.db", "m05_lite_migrate")):
        for worker in ("renderer-1", "renderer-2"):
            args = ["python", "-m", "app.scripts.check_render_worker_removal", "--worker-id", worker, "--format", "json"]
            if database == "architecture_e2e":
                value = drill.compose("exec", "-T", service, *args)
            else:
                value = drill.compose("run", "--rm", "--no-deps", "--entrypoint", "python", service, *args[1:])
            report = json.loads(value)
            assert report["safe_to_remove"] and report["unreleased_attempt_count"] == 0, report
            reports.append({"database": database, **report})
    drill.save("m05-worker-removal-" + str(time.time_ns()) + ".json", {"status": "passed", "checks": reports})

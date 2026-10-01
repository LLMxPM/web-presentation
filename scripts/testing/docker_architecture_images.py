"""文件功能：从固定 Git ref 导出完整源码并构建 M05 旧交付镜像，保留独立锁文件与实际身份。"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile

from docker_architecture_env import ROOT, command


def build(ref: str = "4c7eee8") -> None:
    """只读取 Git 对象，完整旧镜像使用该 ref 的源码、锁文件、Dockerfile 和默认入口。"""
    sha = command("git", "rev-parse", ref)
    destination = ROOT / ".tmp/docker-architecture-images" / sha[:7]
    destination.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(["git", "archive", sha], cwd=ROOT, capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        source.extractall(destination, filter="data")
    output = ROOT / "test-results/docker-architecture-images" / sha[:7]
    output.mkdir(parents=True, exist_ok=True)
    records = {"source_ref": sha, "locks": {name: hashlib.sha256((destination / name).read_bytes()).hexdigest()
                                           for name in ("uv.lock", "pnpm-lock.yaml")}, "images": {}}
    for role, dockerfile in (("lite", "deploy/docker/Dockerfile.lite"), ("platform", "deploy/docker/Dockerfile.platform"),
                             ("runtime", "runtime/Dockerfile"), ("renderer", "renderer/Dockerfile")):
        tag = f"wp-{role}-m05-{sha[:7]}:local"
        print(f"构建 {role}：{sha[:7]}，日志写入 {output.name}/{role}.log", flush=True)
        with (output / f"{role}.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(["docker", "build", "--progress=plain", "-f", str(destination / dockerfile),
                                     "-t", tag, str(destination)], stdout=log, stderr=subprocess.STDOUT, check=False)
        records["images"][role] = {"tag": tag, "exit_code": result.returncode,
                                    "dockerfile_sha256": hashlib.sha256((destination / dockerfile).read_bytes()).hexdigest()}
        if result.returncode == 0:
            records["images"][role]["id"] = command("docker", "image", "inspect", tag, "--format", "{{.Id}}")
        (output / "images.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{role} 构建退出码：{result.returncode}", flush=True)
        if result.returncode:
            raise RuntimeError(f"旧 {role} 镜像构建失败；检查本地构建日志")


if __name__ == "__main__":
    build()

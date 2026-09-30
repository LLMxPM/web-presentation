"""文件功能：在已启动的专用测试拓扑通过 Gateway 验证截图、构建及下载，不启动或重置服务。"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
from zipfile import ZipFile

from deployment_probe_client import ProbeClient
from image_evidence import decode_png


def verify_pipeline(
    client: ProbeClient, *, page_id: int, project_id: int, output: Path, timeout: int
) -> None:
    """只对指定测试页面和项目创建截图/构建任务，保留 ID 与实际下载的 PNG/ZIP。"""
    output.mkdir(parents=True, exist_ok=False)
    report: dict = {"status": "running", "page_id": page_id, "project_id": project_id}

    def save() -> None:
        """逐阶段记录无凭证摘要，失败也保留已创建任务 ID，方便下一轮定位。"""
        (output / "pipeline.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    save()
    try:
        project = client.json(f"api/projects/{project_id}")
        page = client.json(f"api/pages/{page_id}")
        if project["workspace_id"] != page["workspace_id"]:
            raise ValueError("测试页面与项目必须属于同一工作空间")
        # 使用项目默认视口：screenshot_is_latest 要求截图视口与当前项目展示配置一致。
        screenshot = client.json(f"api/pages/{page_id}/screenshot-jobs", {})
        report["screenshot_job_id"] = screenshot["id"]
        save()
        screenshot = client.wait_job(
            f"api/pages/screenshot-jobs/{screenshot['id']}", timeout
        )
        page = client.json(f"api/pages/{page_id}")
        if (
            not page.get("screenshot_is_latest")
            or page.get("screenshot_version_no") != screenshot["target_page_version_no"]
        ):
            raise ValueError("截图不是本轮目标页面版本")
        png = client.fetch(page["screenshot_url"], limit=32 * 1024 * 1024)
        width, height, _rows, _channels = decode_png(png)
        if (width, height) != (
            screenshot["viewport_width"],
            screenshot["viewport_height"],
        ):
            raise ValueError("下载截图尺寸与任务视口不符")
        (output / "page.png").write_bytes(png)
        report["screenshot"] = {
            "sha256": hashlib.sha256(png).hexdigest(),
            "bytes": len(png),
            "width": width,
            "height": height,
            "page_version": page["screenshot_version_no"],
        }
        save()
        build = client.json(f"api/projects/{project_id}/build-jobs", {"base_url": "./"})
        report["build_job_id"] = build["id"]
        save()
        build = client.wait_job(f"api/build-jobs/{build['id']}", timeout)
        content = client.fetch(
            f"api/projects/{project_id}/build-jobs/{build['id']}/artifact",
            limit=256 * 1024 * 1024,
        )
        digest = hashlib.sha256(content).hexdigest()
        if (
            digest != build["artifact_sha256"]
            or len(content) != build["artifact_size_bytes"]
        ):
            raise ValueError("ZIP 下载与构建终态摘要不一致")
        with ZipFile(io.BytesIO(content)) as archive:
            entry = archive.getinfo(build["artifact_entry_file"])
            if entry.file_size > 4 * 1024 * 1024 or not entry.filename.endswith(
                ".html"
            ):
                raise ValueError("ZIP 入口不是有界 HTML")
            html = archive.read(entry).lower()
            if b"<html" not in html or b"<script" not in html:
                raise ValueError("ZIP 缺少 Runtime HTML 入口与脚本引用")
        (output / "build.zip").write_bytes(content)
        report["build"] = {
            "sha256": digest,
            "bytes": len(content),
            "entry": build["artifact_entry_file"],
            "attempt_id": build.get("attempt_id"),
        }
        report["status"] = "passed"
    except Exception:
        report["status"] = "failed"
        raise
    finally:
        save()


def main() -> None:
    """仅使用显式测试目标；账号密码从环境读取，不接受命令行明文凭据。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--page-id", required=True, type=int)
    parser.add_argument("--project-id", required=True, type=int)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    if args.page_id <= 0 or args.project_id <= 0 or args.timeout <= 0:
        parser.error("ID 与超时必须为正数")
    client = ProbeClient(args.base_url)
    client.json(
        "api/auth/login",
        {
            "username": os.environ["WP_SMOKE_USERNAME"],
            "password": os.environ["WP_SMOKE_PASSWORD"],
        },
    )
    verify_pipeline(
        client,
        page_id=args.page_id,
        project_id=args.project_id,
        output=args.output_dir,
        timeout=args.timeout,
    )
    print(f"截图与构建下载通过，证据：{args.output_dir}")


if __name__ == "__main__":
    main()

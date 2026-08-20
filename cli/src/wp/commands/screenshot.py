"""文件功能：提供页面最新截图获取与保存命令，自动触发服务端刷新并返回最新截图。"""

from __future__ import annotations

import os
from pathlib import Path
import uuid

import click

from wp.client import ApiClient, ApiClientError
from wp.config import get_profile, load_config
from wp.formatter import print_error, print_json, print_success, print_table


@click.command("screenshot")
@click.argument("page_id", type=int)
@click.option("--output", "-o", help="截图输出保存路径 (默认保存为 page-<page_id>-v<version>.png)")
@click.pass_context
def screenshot_cmd(
    ctx: click.Context,
    page_id: int,
    output: str | None,
) -> None:
    """获取指定页面的最新截图（像视觉分析工具一样，自动在服务端刷新并返回最新 PNG 截图）。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        page_meta, img_bytes = client.get_latest_page_screenshot(page_id=page_id)

        version_no = page_meta.get("version_no") or 1
        save_path = Path(output) if output else Path(f"page-{page_id}-v{version_no}.png")
        tmp_path = save_path.with_name(f".{save_path.name}.tmp.{uuid.uuid4().hex[:8]}")

        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_bytes(img_bytes)
            os.replace(tmp_path, save_path)
        except OSError as exc:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            print_error(f"写入截图文件 '{save_path}' 失败: {exc}")
            raise SystemExit(1)

        result_payload = {
            "page_id": page_id,
            "version_no": version_no,
            "saved_file": str(save_path.resolve()),
            "size_bytes": len(img_bytes),
        }

        if ctx.obj.get("as_json"):
            print_json(result_payload)
            return

        print_success(f"成功获取页面 (ID: {page_id}) 最新截图并保存至 [bold]{save_path}[/bold]")
        rows = [
            ["页面 ID", str(page_id)],
            ["页面版本", f"v{version_no}"],
            ["文件大小", f"{len(img_bytes)} 字节"],
            ["保存路径", str(save_path.resolve())],
        ]
        print_table("最新页面截图信息", ["属性", "值"], rows)

    except ApiClientError as err:
        print_error(f"获取最新截图失败: {err.message}", code=err.code)
        raise SystemExit(1)

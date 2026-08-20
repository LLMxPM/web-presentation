"""文件功能：处理静态资源管理（列表、详情、上传、下载、归档）。"""

from __future__ import annotations

from pathlib import Path

import click

from wp.client import ApiClient, ApiClientError
from wp.config import get_profile, load_config
from wp.formatter import print_error, print_json, print_success, print_table


@click.group("asset")
def asset_group() -> None:
    """工作空间静态资源管理。"""


ASSET_TYPES = ["image", "icon", "font", "video", "drawio", "mermaid", "chart", "formula"]


@asset_group.command("list")
@click.option("--page", default=1, type=int, help="页码")
@click.option("--page-size", default=50, type=int, help="每页数量")
@click.option("--type", "-t", "asset_type", type=click.Choice(ASSET_TYPES, case_sensitive=False), help="资源类型")
@click.pass_context
def list_assets_cmd(ctx: click.Context, page: int, page_size: int, asset_type: str | None) -> None:
    """查询工作空间的静态资源列表。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        params = {"page": page, "page_size": page_size}
        if asset_type:
            params["asset_type"] = asset_type
        res = client.get("/assets", params=params)
        if ctx.obj.get("as_json"):
            print_json(res)
            return

        items = res.get("items", [])
        rows = [
            [
                a["id"],
                a.get("name", "-"),
                a.get("asset_type", "-"),
                f"{round(a.get('file_size', 0) / 1024, 1)} KB",
                a.get("status", "-"),
            ]
            for a in items
        ]
        print_table("静态资源列表", ["ID", "资源名称", "类型", "文件大小", "状态"], rows)
    except ApiClientError as err:
        print_error(f"获取资源列表失败: {err.message}", code=err.code)
        raise SystemExit(1)


@asset_group.command("upload")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--type", "-t", "asset_type", type=click.Choice(ASSET_TYPES, case_sensitive=False), required=True, help="资源类型")
@click.option("--name", "-n", help="资源名称")
@click.option("--description", "-d", help="资源描述")
@click.pass_context
def upload_asset_cmd(ctx: click.Context, file_path: str, asset_type: str, name: str | None, description: str | None) -> None:
    """上传本地文件到工作空间资源库。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    path_obj = Path(file_path)
    try:
        with path_obj.open("rb") as f:
            files = {"file": (path_obj.name, f)}
            data = {"asset_type": asset_type, "name": name or path_obj.stem, "description": description}
            res = client.upload("/assets", files=files, data=data)

        print_success(f"资源上传成功！资源 ID: [bold]{res.get('id')}[/bold] ({res.get('name')})")
    except ApiClientError as err:
        print_error(f"上传资源失败: {err.message}", code=err.code)
        raise SystemExit(1)


@asset_group.command("archive")
@click.argument("asset_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="跳过确认直接归档")
@click.pass_context
def archive_asset_cmd(ctx: click.Context, asset_id: int, yes: bool) -> None:
    """归档资源。"""

    if not yes and not click.confirm(f"确定要归档资源 ID {asset_id} 吗？"):
        return

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        client.delete(f"/assets/{asset_id}")
        print_success(f"资源 ID {asset_id} 已成功归档。")
    except ApiClientError as err:
        print_error(f"归档资源失败: {err.message}", code=err.code)
        raise SystemExit(1)

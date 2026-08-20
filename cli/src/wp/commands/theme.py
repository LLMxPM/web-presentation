"""文件功能：处理主题管理（列表、详情、创建、复制、归档）。"""

from __future__ import annotations

import click

from wp.client import ApiClient, ApiClientError
from wp.config import get_profile, load_config
from wp.formatter import print_error, print_json, print_success, print_table


@click.group("theme")
def theme_group() -> None:
    """工作空间主题管理。"""


@theme_group.command("list")
@click.option("--page", default=1, type=int, help="页码")
@click.option("--page-size", default=50, type=int, help="每页数量")
@click.pass_context
def list_themes_cmd(ctx: click.Context, page: int, page_size: int) -> None:
    """查询工作空间的主题列表。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        res = client.get("/themes", params={"page": page, "page_size": page_size})
        if ctx.obj.get("as_json"):
            print_json(res)
            return

        items = res.get("items", [])
        rows = [[t["id"], t.get("key", "-"), t.get("name", "-"), t.get("status", "-")] for t in items]
        print_table("主题列表", ["ID", "Key", "名称", "状态"], rows)
    except ApiClientError as err:
        print_error(f"获取主题列表失败: {err.message}", code=err.code)
        raise SystemExit(1)


@theme_group.command("get")
@click.argument("theme_id", type=int)
@click.pass_context
def get_theme_cmd(ctx: click.Context, theme_id: int) -> None:
    """获取单个主题详情。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        theme = client.get(f"/themes/{theme_id}")
        if ctx.obj.get("as_json"):
            print_json(theme)
            return

        rows = [
            ["ID", str(theme.get("id"))],
            ["Key", str(theme.get("key"))],
            ["名称", str(theme.get("name"))],
            ["描述", str(theme.get("description") or "-")],
            ["状态", str(theme.get("status"))],
        ]
        print_table(f"主题 (ID: {theme_id}) 详情", ["属性", "值"], rows)
    except ApiClientError as err:
        print_error(f"获取主题失败: {err.message}", code=err.code)
        raise SystemExit(1)


@theme_group.command("create")
@click.option("--key", "-k", required=True, help="主题唯一标识 (例如 light-corporate)")
@click.option("--name", "-n", required=True, help="主题名称")
@click.option("--description", "-d", help="主题描述")
@click.pass_context
def create_theme_cmd(ctx: click.Context, key: str, name: str, description: str | None) -> None:
    """创建新主题。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        payload = {"key": key, "name": name, "description": description}
        theme = client.post("/themes", json_data=payload)
        print_success(f"主题创建成功！主题 ID: [bold]{theme.get('id')}[/bold] (Key: {theme.get('key')})")
    except ApiClientError as err:
        print_error(f"创建主题失败: {err.message}", code=err.code)
        raise SystemExit(1)


@theme_group.command("archive")
@click.argument("theme_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="跳过确认直接归档")
@click.pass_context
def archive_theme_cmd(ctx: click.Context, theme_id: int, yes: bool) -> None:
    """归档主题。"""

    if not yes and not click.confirm(f"确定要归档主题 ID {theme_id} 吗？"):
        return

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        client.delete(f"/themes/{theme_id}")
        print_success(f"主题 ID {theme_id} 已成功归档。")
    except ApiClientError as err:
        print_error(f"归档主题失败: {err.message}", code=err.code)
        raise SystemExit(1)

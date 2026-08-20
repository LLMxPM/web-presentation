"""文件功能：处理样式方案管理（列表、详情、创建、复制、归档）。"""

from __future__ import annotations

import click

from wp.client import ApiClient, ApiClientError
from wp.config import get_profile, load_config
from wp.formatter import print_error, print_json, print_success, print_table


@click.group("style")
def style_group() -> None:
    """工作空间样式方案管理。"""


@style_group.command("list")
@click.option("--page", default=1, type=int, help="页码")
@click.option("--page-size", default=50, type=int, help="每页数量")
@click.pass_context
def list_styles_cmd(ctx: click.Context, page: int, page_size: int) -> None:
    """查询工作空间的样式方案列表。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        res = client.get("/styles", params={"page": page, "page_size": page_size})
        if ctx.obj.get("as_json"):
            print_json(res)
            return

        items = res.get("items", [])
        rows = [[s["id"], s.get("name", "-"), s.get("is_default", False), s.get("status", "-")] for s in items]
        print_table("样式方案列表", ["ID", "名称", "是否默认", "状态"], rows)
    except ApiClientError as err:
        print_error(f"获取样式列表失败: {err.message}", code=err.code)
        raise SystemExit(1)


@style_group.command("get")
@click.argument("style_id", type=int)
@click.pass_context
def get_style_cmd(ctx: click.Context, style_id: int) -> None:
    """获取单个样式方案详情。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        style = client.get(f"/styles/{style_id}")
        if ctx.obj.get("as_json"):
            print_json(style)
            return

        rows = [
            ["ID", str(style.get("id"))],
            ["名称", str(style.get("name"))],
            ["是否默认", str(style.get("is_default"))],
            ["描述", str(style.get("description") or "-")],
            ["状态", str(style.get("status"))],
        ]
        print_table(f"样式方案 (ID: {style_id}) 详情", ["属性", "值"], rows)
    except ApiClientError as err:
        print_error(f"获取样式方案失败: {err.message}", code=err.code)
        raise SystemExit(1)


@style_group.command("create")
@click.option("--name", "-n", required=True, help="样式方案名称")
@click.option("--description", "-d", help="样式描述")
@click.pass_context
def create_style_cmd(ctx: click.Context, name: str, description: str | None) -> None:
    """创建新样式方案。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        payload = {"name": name, "description": description}
        style = client.post("/styles", json_data=payload)
        print_success(f"样式方案创建成功！样式 ID: [bold]{style.get('id')}[/bold] ({style.get('name')})")
    except ApiClientError as err:
        print_error(f"创建样式方案失败: {err.message}", code=err.code)
        raise SystemExit(1)


@style_group.command("archive")
@click.argument("style_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="跳过确认直接归档")
@click.pass_context
def archive_style_cmd(ctx: click.Context, style_id: int, yes: bool) -> None:
    """归档样式方案（默认样式受保护禁止归档）。"""

    if not yes and not click.confirm(f"确定要归档样式 ID {style_id} 吗？"):
        return

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        client.delete(f"/styles/{style_id}")
        print_success(f"样式方案 ID {style_id} 已成功归档。")
    except ApiClientError as err:
        print_error(f"归档样式方案失败: {err.message}", code=err.code)
        raise SystemExit(1)

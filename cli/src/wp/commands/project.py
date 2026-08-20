"""文件功能：处理项目管理（列表、详情、创建、更新、归档）。"""

from __future__ import annotations

import click

from wp.client import ApiClient, ApiClientError
from wp.config import get_profile, load_config
from wp.formatter import print_error, print_json, print_success, print_table


@click.group("project")
def project_group() -> None:
    """项目管理操作。"""


@project_group.command("list")
@click.option("--page", "-p", default=1, type=int, help="页码")
@click.option("--page-size", "-s", default=20, type=int, help="每页数量")
@click.option("--keyword", "-k", help="搜索关键字")
@click.pass_context
def list_projects_cmd(ctx: click.Context, page: int, page_size: int, keyword: str | None) -> None:
    """查询工作空间内的项目列表。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        params = {"page": page, "page_size": page_size}
        if keyword:
            params["keyword"] = keyword
        res = client.get("/projects", params=params)
        if ctx.obj.get("as_json"):
            print_json(res)
            return

        items = res.get("items", [])
        rows = [[p["id"], p["name"], p.get("status", "-"), p.get("created_at", "-")[:19]] for p in items]
        print_table(f"项目列表 (共 {res.get('total', len(items))} 项)", ["ID", "项目名称", "状态", "创建时间"], rows)
    except ApiClientError as err:
        print_error(f"获取项目列表失败: {err.message}", code=err.code)
        raise SystemExit(1)


@project_group.command("get")
@click.argument("project_id", type=int)
@click.pass_context
def get_project_cmd(ctx: click.Context, project_id: int) -> None:
    """获取单个项目详情。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        project = client.get(f"/projects/{project_id}")
        if ctx.obj.get("as_json"):
            print_json(project)
            return

        print_success(f"项目详情: [bold]{project.get('name')}[/bold] (ID: {project_id})")
        rows = [
            ["ID", str(project.get("id"))],
            ["名称", str(project.get("name"))],
            ["描述", str(project.get("description") or "-")],
            ["工作空间 ID", str(project.get("workspace_id"))],
            ["主题 ID", str(project.get("theme_id") or "-")],
            ["样式 ID", str(project.get("style_id") or "-")],
            ["状态", str(project.get("status"))],
            ["创建时间", str(project.get("created_at"))],
        ]
        print_table("基本属性", ["字段", "值"], rows)
    except ApiClientError as err:
        print_error(f"获取项目详情失败: {err.message}", code=err.code)
        raise SystemExit(1)


@project_group.command("create")
@click.option("--name", "-n", required=True, help="项目名称")
@click.option("--description", "-d", help="项目描述")
@click.pass_context
def create_project_cmd(ctx: click.Context, name: str, description: str | None) -> None:
    """创建新项目。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        payload = {"name": name, "description": description}
        project = client.post("/projects", json_data=payload)
        if ctx.obj.get("as_json"):
            print_json(project)
            return

        print_success(f"项目创建成功: [bold]{project.get('name')}[/bold] (ID: {project.get('id')})")
    except ApiClientError as err:
        print_error(f"创建项目失败: {err.message}", code=err.code)
        raise SystemExit(1)


@project_group.command("archive")
@click.argument("project_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="跳过确认直接归档")
@click.pass_context
def archive_project_cmd(ctx: click.Context, project_id: int, yes: bool) -> None:
    """归档项目。"""

    if not yes and not click.confirm(f"确定要归档项目 ID {project_id} 吗？"):
        return

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        client.delete(f"/projects/{project_id}")
        print_success(f"项目 ID {project_id} 已成功归档。")
    except ApiClientError as err:
        print_error(f"归档项目失败: {err.message}", code=err.code)
        raise SystemExit(1)

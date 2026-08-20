"""文件功能：处理工作空间组件管理（列表、详情、草稿、创建、发布、归档）。"""

from __future__ import annotations

from pathlib import Path

import click

from wp.client import ApiClient, ApiClientError
from wp.config import get_profile, load_config
from wp.formatter import print_code, print_error, print_json, print_success, print_table


@click.group("component")
def component_group() -> None:
    """工作空间组件管理与 Mutation 任务。"""


@component_group.command("list")
@click.option("--page", default=1, type=int, help="页码")
@click.option("--page-size", default=50, type=int, help="每页数量")
@click.option("--keyword", "-k", help="搜索关键字")
@click.pass_context
def list_components_cmd(ctx: click.Context, page: int, page_size: int, keyword: str | None) -> None:
    """查询工作空间组件列表。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        res = client.get("/components", params={"page": page, "page_size": page_size, "keyword": keyword})
        if ctx.obj.get("as_json"):
            print_json(res)
            return

        items = res.get("items", [])
        rows = [
            [
                c["id"],
                c.get("import_name", "-"),
                c.get("name", "-"),
                c.get("component_type", "-"),
                f"v{c.get('current_version_no', 1)}",
                c.get("status", "-"),
            ]
            for c in items
        ]
        print_table("工作空间组件列表", ["ID", "导入标识", "名称", "类型", "版本", "状态"], rows)
    except ApiClientError as err:
        print_error(f"获取组件列表失败: {err.message}", code=err.code)
        raise SystemExit(1)


@component_group.command("get")
@click.argument("component_id", type=int)
@click.pass_context
def get_component_cmd(ctx: click.Context, component_id: int) -> None:
    """获取单个组件详情。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        comp = client.get(f"/components/{component_id}")
        if ctx.obj.get("as_json"):
            print_json(comp)
            return

        rows = [
            ["ID", str(comp.get("id"))],
            ["导入标识", str(comp.get("import_name"))],
            ["组件名称", str(comp.get("name"))],
            ["组件类型", str(comp.get("component_type"))],
            ["当前版本", f"v{comp.get('current_version_no')}"],
            ["状态", str(comp.get("status"))],
            ["创建时间", str(comp.get("created_at"))],
        ]
        print_table(f"组件 (ID: {component_id}) 详情", ["属性", "值"], rows)
    except ApiClientError as err:
        print_error(f"获取组件失败: {err.message}", code=err.code)
        raise SystemExit(1)


@component_group.command("draft")
@click.argument("component_id", type=int)
@click.pass_context
def get_component_draft_cmd(ctx: click.Context, component_id: int) -> None:
    """查看组件当前的草稿源码。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        draft = client.get(f"/components/{component_id}/draft")
        if ctx.obj.get("as_json"):
            print_json(draft)
            return

        code = draft.get("content", "")
        print_code(code, lexer="vue", title=f"组件 ID {component_id} ({draft.get('import_name')}) 草稿源码")
    except ApiClientError as err:
        print_error(f"读取组件草稿失败: {err.message}", code=err.code)
        raise SystemExit(1)


@component_group.command("create")
@click.option("--name", "-n", required=True, help="组件展示名称")
@click.option("--import-name", "-i", required=True, help="组件导入标识 (PascalCase)")
@click.option("--file", "-f", "file_path", required=True, type=click.Path(exists=True), help="Vue 源码文件路径")
@click.option("--type", "-t", "comp_type", default="content", help="组件类型 (content, card, section, template, custom, page, atomic)")
@click.option("--description", "-d", help="组件描述")
@click.option("--wait/--no-wait", default=True, help="是否等待后台 Worker 诊断完成")
@click.pass_context
def create_component_cmd(
    ctx: click.Context,
    name: str,
    import_name: str,
    file_path: str,
    comp_type: str,
    description: str | None,
    wait: bool,
) -> None:
    """通过异步 Mutation 任务创建工作空间组件。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    ws_id = ctx.obj.get("workspace_id") or profile.default_workspace_id
    if not ws_id:
        print_error("未指定工作空间 ID。")
        raise SystemExit(1)

    client = ApiClient(profile, workspace_id=ws_id)
    try:
        source_code = Path(file_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print_error(f"无法读取文件 '{file_path}': {exc}")
        raise SystemExit(1)
    payload = {
        "workspace_id": ws_id,
        "import_name": import_name,
        "name": name,
        "component_type": comp_type,
        "source_code": source_code,
        "description": description,
    }

    try:
        job = client.post("/jobs/mutations/components", json_data=payload)
        job_id = job.get("job_id")
        print_success(f"组件创建任务已提交 (Job ID: [bold]{job_id}[/bold])")

        if not wait:
            if ctx.obj.get("as_json"):
                print_json(job)
            return

        with click.progressbar(length=100, label="Worker 正在执行无锁规划与组件诊断...") as bar:
            final_job = client.poll_mutation_job(job_id, timeout_seconds=60.0)
            bar.update(100)

        if final_job.get("status") == "succeeded":
            res = final_job.get("result", {})
            print_success(f"组件创建成功！组件 ID: [bold]{res.get('component_id')}[/bold] ({res.get('import_name')})")
        else:
            err = final_job.get("error", {})
            print_error(f"组件创建失败: {err.get('message')}", code=err.get("code"))
            raise SystemExit(1)
    except ApiClientError as err:
        print_error(f"提交组件任务失败: {err.message}", code=err.code)
        raise SystemExit(1)


@component_group.command("publish")
@click.argument("component_id", type=int)
@click.option("--release-name", "-r", help="发布版本标签")
@click.option("--change-note", "-m", help="版本更新说明")
@click.pass_context
def publish_component_cmd(
    ctx: click.Context, component_id: int, release_name: str | None, change_note: str | None
) -> None:
    """发布组件当前草稿为可引用的正式版本。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        payload = {"release_name": release_name, "change_note": change_note}
        comp = client.post(f"/components/{component_id}/publish", json_data=payload)
        print_success(f"组件已成功发布新版本！当前版本: [bold]v{comp.get('current_version_no')}[/bold]")
    except ApiClientError as err:
        print_error(f"发布组件失败: {err.message}", code=err.code)
        raise SystemExit(1)


@component_group.command("archive")
@click.argument("component_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="跳过确认直接归档")
@click.pass_context
def archive_component_cmd(ctx: click.Context, component_id: int, yes: bool) -> None:
    """归档组件。"""

    if not yes and not click.confirm(f"确定要归档组件 ID {component_id} 吗？"):
        return

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        client.delete(f"/components/{component_id}")
        print_success(f"组件 ID {component_id} 已成功归档。")
    except ApiClientError as err:
        print_error(f"归档组件失败: {err.message}", code=err.code)
        raise SystemExit(1)

"""文件功能：处理页面管理（列表、详情、源码查看、异步创建与归档）。"""

from __future__ import annotations

from pathlib import Path

import click

from wp.client import ApiClient, ApiClientError
from wp.commands.screenshot import screenshot_cmd
from wp.config import get_profile, load_config
from wp.formatter import print_code, print_error, print_json, print_success, print_table



@click.group("page")
def page_group() -> None:
    """页面管理与 Mutation 任务。"""


@page_group.command("list")
@click.option("--project-id", "-p", required=True, type=int, help="项目 ID")
@click.option("--page", default=1, type=int, help="页码")
@click.option("--page-size", default=50, type=int, help="每页数量")
@click.pass_context
def list_pages_cmd(ctx: click.Context, project_id: int, page: int, page_size: int) -> None:
    """查询指定项目下的页面列表。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        res = client.get(f"/projects/{project_id}/pages", params={"page": page, "page_size": page_size})
        if ctx.obj.get("as_json"):
            print_json(res)
            return

        items = res.get("items", [])
        rows = [[p["id"], p.get("code", "-"), p.get("title", "-"), f"v{p.get('current_version_no', 1)}", p.get("status", "-")] for p in items]
        print_table(f"项目 (ID: {project_id}) 页面列表", ["ID", "编码", "标题", "版本", "状态"], rows)
    except ApiClientError as err:
        print_error(f"获取页面列表失败: {err.message}", code=err.code)
        raise SystemExit(1)


@page_group.command("get")
@click.argument("page_id", type=int)
@click.pass_context
def get_page_cmd(ctx: click.Context, page_id: int) -> None:
    """获取指定页面的元数据详情。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        page = client.get(f"/pages/{page_id}")
        if ctx.obj.get("as_json"):
            print_json(page)
            return

        rows = [
            ["ID", str(page.get("id"))],
            ["编码", str(page.get("code"))],
            ["标题", str(page.get("title"))],
            ["所属项目 ID", str(page.get("project_id"))],
            ["当前版本", f"v{page.get('current_version_no')}"],
            ["状态", str(page.get("status"))],
            ["创建时间", str(page.get("created_at"))],
        ]
        print_table(f"页面 (ID: {page_id}) 详情", ["属性", "值"], rows)
    except ApiClientError as err:
        print_error(f"获取页面失败: {err.message}", code=err.code)
        raise SystemExit(1)


@page_group.command("source")
@click.argument("page_id", type=int)
@click.pass_context
def get_page_source_cmd(ctx: click.Context, page_id: int) -> None:
    """查看指定页面的当前 Vue SFC 源码。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        data = client.get(f"/pages/{page_id}/source")
        if ctx.obj.get("as_json"):
            print_json(data)
            return

        code = data.get("source_code", "")
        print_code(code, lexer="vue", title=f"页面 ID {page_id} 源码 (v{data.get('version_no')})")
    except ApiClientError as err:
        print_error(f"读取页面源码失败: {err.message}", code=err.code)
        raise SystemExit(1)


@page_group.command("create")
@click.option("--project-id", "-p", required=True, type=int, help="所属项目 ID")
@click.option("--name", "-n", required=True, help="页面标题")
@click.option("--file", "-f", "file_path", required=True, type=click.Path(exists=True), help="Vue 源码文件路径")
@click.option("--description", "-d", help="页面描述")
@click.option("--wait/--no-wait", default=True, help="是否等待后台 Worker 编译与诊断完成 (默认等待)")
@click.pass_context
def create_page_cmd(
    ctx: click.Context,
    project_id: int,
    name: str,
    file_path: str,
    description: str | None,
    wait: bool,
) -> None:
    """通过异步 Mutation 任务创建页面（带 AST 扫描与 Chromium 慢诊断）。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        source_code = Path(file_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print_error(f"无法读取文件 '{file_path}': {exc}")
        raise SystemExit(1)
    payload = {
        "project_id": project_id,
        "name": name,
        "source_code": source_code,
        "description": description,
    }

    try:
        job = client.post("/jobs/mutations/pages", json_data=payload)
        job_id = job.get("job_id")
        print_success(f"页面创建任务已提交 (Job ID: [bold]{job_id}[/bold])")

        if not wait:
            if ctx.obj.get("as_json"):
                print_json(job)
            return

        with click.progressbar(length=100, label="Worker 正在执行无锁规划与慢诊断...") as bar:
            final_job = client.poll_mutation_job(job_id, timeout_seconds=60.0)
            bar.update(100)

        if final_job.get("status") == "succeeded":
            result = final_job.get("result", {})
            print_success(f"页面创建成功！页面 ID: [bold]{result.get('page_id')}[/bold] (版本: v{result.get('version_no')})")
        else:
            err = final_job.get("error", {})
            print_error(f"页面创建失败: {err.get('message')}", code=err.get("code"))
            raise SystemExit(1)
    except ApiClientError as err:
        print_error(f"提交页面任务失败: {err.message}", code=err.code)
        raise SystemExit(1)


@page_group.command("archive")
@click.argument("page_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="跳过确认直接归档")
@click.pass_context
def archive_page_cmd(ctx: click.Context, page_id: int, yes: bool) -> None:
    """归档页面。"""

    if not yes and not click.confirm(f"确定要归档页面 ID {page_id} 吗？"):
        return

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        client.delete(f"/pages/{page_id}")
        print_success(f"页面 ID {page_id} 已成功归档。")
    except ApiClientError as err:
        print_error(f"归档页面失败: {err.message}", code=err.code)
        raise SystemExit(1)


page_group.add_command(screenshot_cmd)

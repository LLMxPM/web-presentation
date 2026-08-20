"""文件功能：处理工作空间列表查询、默认空间切换与能力矩阵发现。"""

from __future__ import annotations

import click

from wp.client import ApiClient, ApiClientError
from wp.config import get_profile, load_config, save_config
from wp.formatter import print_error, print_json, print_success, print_table


@click.group("workspace")
def workspace_group() -> None:
    """工作空间操作。"""


@workspace_group.command("list")
@click.pass_context
def list_workspaces_cmd(ctx: click.Context) -> None:
    """列出当前令牌可访问的所有工作空间。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile)

    try:
        workspaces = client.get("/workspaces")
        if ctx.obj.get("as_json"):
            print_json(workspaces)
            return

        current_ws_id = profile.default_workspace_id
        rows = []
        for w in workspaces:
            is_curr = "*" if w["id"] == current_ws_id else ""
            rows.append([f"{is_curr} {w['id']}", w["name"], w.get("code") or "-", w.get("status")])

        print_table("授权工作空间 (* 当前默认)", ["ID", "名称", "Code", "状态"], rows)
    except ApiClientError as err:
        print_error(f"获取工作空间失败: {err.message}", code=err.code)
        raise SystemExit(1)


@workspace_group.command("use")
@click.argument("workspace_id", type=int)
@click.pass_context
def use_workspace_cmd(ctx: click.Context, workspace_id: int) -> None:
    """切换本地默认操作的工作空间 ID。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile)

    try:
        ws = client.get(f"/workspaces/{workspace_id}")
        profile.default_workspace_id = workspace_id
        save_config(cfg)
        print_success(f"已将默认工作空间切换为: [bold]{ws.get('name')}[/bold] (ID: {workspace_id})")
    except ApiClientError as err:
        print_error(f"切换工作空间失败: {err.message}", code=err.code)
        raise SystemExit(1)


@workspace_group.command("capabilities")
@click.option("--workspace-id", "-w", type=int, help="工作空间 ID")
@click.pass_context
def get_capabilities_cmd(ctx: click.Context, workspace_id: int | None) -> None:
    """查询当前令牌在指定工作空间的能力矩阵与可用操作列表。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    ws_id = workspace_id or ctx.obj.get("workspace_id") or profile.default_workspace_id
    if not ws_id:
        print_error("未指定工作空间 ID，请先使用 `wp workspace use <id>` 或提供 `-w <id>`。")
        raise SystemExit(1)

    client = ApiClient(profile, workspace_id=ws_id)
    try:
        caps = client.get(f"/workspaces/{ws_id}/capabilities")
        if ctx.obj.get("as_json"):
            print_json(caps)
            return

        print_success(f"工作空间 (ID: {ws_id}) 权限能力:")
        print_table("授权 Scope", ["Scope 标识"], [[s] for s in caps.get("scopes", [])])
        print_table("可用操作 (Operations)", ["操作 Key"], [[op] for op in caps.get("operations", [])])
    except ApiClientError as err:
        print_error(f"查询能力矩阵失败: {err.message}", code=err.code)
        raise SystemExit(1)

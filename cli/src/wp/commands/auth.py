"""文件功能：处理 CLI 用户登录、PAT 凭证持久化与身份检查。"""

from __future__ import annotations

import click

from wp.client import ApiClient, ApiClientError
from wp.config import get_profile, load_config, save_config
from wp.formatter import print_error, print_json, print_success, print_table


@click.command("login")
@click.option("--token", "-t", required=True, prompt=True, hide_input=True, help="个人访问令牌 (PAT)")
@click.option("--endpoint", "-e", help="Backend 服务地址 (默认 http://127.0.0.1:8000)")
@click.pass_context
def login_cmd(ctx: click.Context, token: str, endpoint: str | None) -> None:
    """登录并保存个人访问令牌 (PAT)。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    if endpoint:
        profile.endpoint = endpoint
    profile.token = token.strip()

    client = ApiClient(profile)
    try:
        workspaces = client.get("/workspaces")
        if workspaces:
            profile.default_workspace_id = workspaces[0]["id"]
        save_config(cfg)
        print_success(f"登录成功！已连接到 {profile.endpoint}，授权工作空间数: {len(workspaces)}")
    except ApiClientError as err:
        print_error(f"PAT 验证失败: {err.message}", code=err.code)
        raise SystemExit(1)


@click.command("logout")
@click.pass_context
def logout_cmd(ctx: click.Context) -> None:
    """清除当前 Profile 的访问令牌。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    profile.token = None
    profile.default_workspace_id = None
    save_config(cfg)
    print_success("已安全清除本地保存的访问令牌。")


@click.command("whoami")
@click.pass_context
def whoami_cmd(ctx: click.Context) -> None:
    """检查当前认证状态与权限能力。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        workspaces = client.get("/workspaces")
        if ctx.obj.get("as_json"):
            print_json({"endpoint": profile.endpoint, "workspaces": workspaces})
            return

        print_success(f"当前环境: [bold]{profile.endpoint}[/bold]")
        print_table(
            title="已授权工作空间",
            columns=["ID", "空间名称", "所有者 ID", "状态"],
            rows=[[w["id"], w["name"], w.get("owner_id"), w.get("status")] for w in workspaces],
        )
    except ApiClientError as err:
        print_error(f"查询失败: {err.message}", code=err.code)
        raise SystemExit(1)

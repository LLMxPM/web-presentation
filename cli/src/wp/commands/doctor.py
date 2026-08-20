"""文件功能：执行 CLI 诊断（连通性、PAT 有效性、默认空间与权限检测）。"""

from __future__ import annotations

import click
import httpx

import wp
from wp.client import ApiClient, ApiClientError
from wp.config import get_profile, load_config
from wp.formatter import print_json, print_table


@click.command("doctor")
@click.pass_context
def doctor_cmd(ctx: click.Context) -> None:
    """全面诊断本地 CLI 环境、服务连通性与 PAT 授权状态。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    diagnostics = []

    # 1. CLI 版本
    diagnostics.append(["CLI 版本", f"v{wp.__version__}", "[green]正常[/green]"])

    # 2. 服务端探活
    endpoint = profile.endpoint.rstrip("/")
    health_status = "[red]不可达[/red]"
    try:
        r = httpx.get(f"{endpoint}/healthz", timeout=5.0)
        if r.status_code == 200:
            health_status = "[green]在线[/green]"
    except Exception:
        pass
    diagnostics.append(["Backend 地址", endpoint, health_status])

    # 3. PAT 凭证检测
    token_status = "[yellow]未配置[/yellow]"
    if profile.token:
        token_status = f"[green]已配置[/green] ({profile.token[:12]}...)"
    diagnostics.append(["访问令牌 (PAT)", token_status, "[green]OK[/green]" if profile.token else "[yellow]待配置[/yellow]"])

    # 4. API 连通与权限校验
    if profile.token:
        client = ApiClient(profile)
        try:
            workspaces = client.get("/workspaces")
            diagnostics.append(["授权工作空间", f"{len(workspaces)} 个可用空间", "[green]通过[/green]"])
        except ApiClientError as err:
            diagnostics.append(["API 认证", f"认证失败: {err.message}", "[red]失败[/red]"])

        ws_id = profile.default_workspace_id
        if ws_id:
            try:
                ws = client.get(f"/workspaces/{ws_id}")
                diagnostics.append(["默认工作空间", f"{ws.get('name')} (ID: {ws_id})", "[green]有效[/green]"])
            except ApiClientError:
                diagnostics.append(["默认工作空间", f"访问受限 (ID: {ws_id})", "[red]失效[/red]"])
        else:
            diagnostics.append(["默认工作空间", "未设置", "[yellow]提示: 使用 wp workspace use <id>[/yellow]"])

    if ctx.obj.get("as_json"):
        print_json(diagnostics)
        return

    print_table("CLI 诊断检查报告", ["检查项", "当前状态", "判定结果"], diagnostics)

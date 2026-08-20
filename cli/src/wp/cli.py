"""文件功能：CLI 总入口，注册全局选项与全部资源子命令。"""

from __future__ import annotations

import click

from wp.commands.asset import asset_group
from wp.commands.auth import login_cmd, logout_cmd, whoami_cmd
from wp.commands.build import build_group
from wp.commands.component import component_group
from wp.commands.doctor import doctor_cmd
from wp.commands.page import page_group
from wp.commands.project import project_group
from wp.commands.screenshot import screenshot_cmd
from wp.commands.style import style_group
from wp.commands.theme import theme_group
from wp.commands.validate import validate_cmd
from wp.commands.workspace import workspace_group


@click.group()
@click.option("--json", "as_json", is_flag=True, help="以 JSON 格式输出机器可读数据")
@click.option("--profile", help="指定使用的 Profile 名称 (默认 default)")
@click.option("--workspace", "-w", "workspace_id", type=int, help="覆盖当前操作的目标工作空间 ID")
@click.pass_context
def main(ctx: click.Context, as_json: bool, profile: str | None, workspace_id: int | None) -> None:
    """Web Presentation 官方命令行工具 (wp) - 面向 AI 演示文稿创作平台。"""

    ctx.ensure_object(dict)
    ctx.obj["as_json"] = as_json
    ctx.obj["profile"] = profile
    ctx.obj["workspace_id"] = workspace_id


# 注册认证与系统命令
main.add_command(login_cmd)
main.add_command(logout_cmd)
main.add_command(whoami_cmd)
main.add_command(doctor_cmd)
main.add_command(validate_cmd)
main.add_command(screenshot_cmd)


# 注册各实体资源命令组
main.add_command(workspace_group)
main.add_command(project_group)
main.add_command(page_group)
main.add_command(component_group)
main.add_command(asset_group)
main.add_command(theme_group)
main.add_command(style_group)
main.add_command(build_group)


if __name__ == "__main__":
    main()

"""文件功能：对本地 Vue 页面或工作空间组件源码进行语法与 Runtime Kit 合法性预检。"""

from __future__ import annotations

from pathlib import Path

import click

from wp.client import ApiClient, ApiClientError
from wp.config import get_profile, load_config
from wp.formatter import print_error, print_json, print_success, print_table


@click.command("validate")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--type", "-t", "entity_type", type=click.Choice(["page", "component"]), default="page", help="待校验代码类型 (默认 page)")
@click.pass_context
def validate_cmd(ctx: click.Context, file_path: str, entity_type: str) -> None:
    """独立校验 Vue 页面或组件源码的合法性与 @runtime-kit 依赖规范。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        code = Path(file_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print_error(f"无法读取文件 '{file_path}': {exc}")
        raise SystemExit(1)
    payload = {
        "entity_type": entity_type,
        "source_code": code,
    }

    try:
        res = client.post("/validate/code", json_data=payload, idempotent=False)
        if ctx.obj.get("as_json"):
            print_json(res)
            return

        is_valid = res.get("valid", False)
        if is_valid:
            print_success(f"代码校验通过！[bold]{file_path}[/bold] 符合 SFC 语法与 Runtime Kit 契约。")
            imports = res.get("imports", [])
            if imports:
                print_table("检测到的模块依赖", ["导入路径"], [[imp] for imp in imports])
        else:
            print_error(f"代码校验未通过: [bold]{file_path}[/bold]")
            errors = res.get("errors", [])
            print_table("错误列表", ["错误原因"], [[err] for err in errors])
            raise SystemExit(1)

        warnings = res.get("warnings", [])
        if warnings:
            print_table("警告提示", ["警告信息"], [[warn] for warn in warnings])
    except ApiClientError as err:
        print_error(f"校验请求失败: {err.message}", code=err.code)
        raise SystemExit(1)

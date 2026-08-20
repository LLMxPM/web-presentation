"""文件功能：提供 Rich 终端美化输出与 JSON 统一格式化。"""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

console = Console()
err_console = Console(stderr=True)


def print_json(data: Any) -> None:
    """输出 JSON 格式数据。"""

    console.print_json(data=data if isinstance(data, (dict, list)) else json.loads(str(data)))


def print_success(message: str) -> None:
    """输出成功提示。"""

    console.print(f"[bold green]✔[/bold green] {message}")


def print_error(message: str, code: str | None = None, details: Any = None) -> None:
    """输出错误提示。"""

    prefix = f"[{code}] " if code else ""
    err_console.print(f"[bold red]✖[/bold red] [red]{prefix}{message}[/red]")
    if details:
        err_console.print(f"[dim]详细信息: {details}[/dim]")


def print_table(title: str, columns: list[str], rows: list[list[Any]]) -> None:
    """输出美化表格。"""

    table = Table(title=title, show_header=True, header_style="bold cyan")
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*[str(cell) if cell is not None else "-" for cell in row])
    console.print(table)


def print_code(code: str, lexer: str = "vue", title: str | None = None) -> None:
    """输出带语法高亮的代码块。"""

    syntax = Syntax(code, lexer, theme="monokai", line_numbers=True)
    if title:
        console.print(Panel(syntax, title=title, border_style="dim"))
    else:
        console.print(syntax)

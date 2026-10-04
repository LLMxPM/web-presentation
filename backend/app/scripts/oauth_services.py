"""文件功能：管理预注册 MCP 服务身份，秘密只从受控文件读取且不进入输出或命令行参数。"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.core.config import get_settings
from app.core.oauth_config import resolve_oauth_policy
from app.db.session import get_session_factory, reset_database_state
from app.services.oauth.service_registry import OAuthServiceRegistry


def read_service_secret(path: Path) -> str:
    """限制 Secret 文件大小，只去掉一个末尾换行，其余空白由登记校验拒绝。"""
    with path.open("rb") as source:
        data = source.read(1025)
    if len(data) > 1024:
        raise ValueError("服务密钥文件过大。")
    return data.decode("ascii").removesuffix("\n").removesuffix("\r")


async def run_command(args: argparse.Namespace) -> object:
    """从根仓配置校验信任边界，按明确子命令执行；数据库错误由 CLI 安全收敛。"""
    policy = resolve_oauth_policy(get_settings())
    if policy is None:
        raise ValueError("请在运维进程显式启用并配置 OAuth。")
    registry = OAuthServiceRegistry(get_session_factory(), policy)
    if args.command == "list":
        return [row.to_dict() for row in await registry.list_services()]
    if args.command == "disable":
        row = await registry.disable(args.service_id)
    else:
        secret = read_service_secret(args.secret_file)
        if args.command == "create":
            row = await registry.create(args.service_id, args.name, secret)
        else:
            row = await registry.rotate(args.service_id, secret, enable=args.enable)
    return row.to_dict()


def build_parser() -> argparse.ArgumentParser:
    """只开放公共标识和 Secret 文件路径；源/目标地址固定复用部署配置。"""
    parser = argparse.ArgumentParser(
        description="受信 MCP 服务登记、密钥轮换和停用。", allow_abbrev=False
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="列出公共登记信息", allow_abbrev=False)
    create = commands.add_parser(
        "create", help="创建新的启用服务，不覆盖现有 ID", allow_abbrev=False
    )
    create.add_argument("--service-id", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--secret-file", type=Path, required=True)
    rotate = commands.add_parser(
        "rotate", help="立即替换密钥，默认保留停用状态", allow_abbrev=False
    )
    rotate.add_argument("--service-id", required=True)
    rotate.add_argument("--secret-file", type=Path, required=True)
    rotate.add_argument("--enable", action="store_true", help="显式重新启用停用服务")
    disable = commands.add_parser(
        "disable", help="停用并撤销已签发委托", allow_abbrev=False
    )
    disable.add_argument("--service-id", required=True)
    return parser


async def _run(args: argparse.Namespace) -> object:
    """完成运维后释放数据库连接，方便重复 CLI 调用与测试隔离。"""
    try:
        return await run_command(args)
    finally:
        await reset_database_state()


def main(argv: list[str] | None = None) -> int:
    """成功输出公共 JSON；失败仅输出固定消息和异常类型，不打印数据库参数或 Secret。"""
    args = build_parser().parse_args(argv)
    try:
        result = asyncio.run(_run(args))
    except Exception as error:  # noqa: BLE001 - 运维错误不能携带凭证参数
        print(
            f"OAuth 服务运维失败（{type(error).__name__}），请核对配置、ID 和 Secret 文件。",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

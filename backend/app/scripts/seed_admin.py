"""文件功能：提供命令行种子脚本，用于初始化默认管理员账号。"""

import asyncio

from app.db.session import get_session_factory
from app.services.bootstrap_service import BootstrapService


async def _main() -> None:
    """执行默认管理员初始化逻辑。"""

    await BootstrapService(get_session_factory()).ensure_default_admin()


def main() -> None:
    """同步入口，便于通过项目脚本直接调用。"""

    asyncio.run(_main())


if __name__ == "__main__":
    main()

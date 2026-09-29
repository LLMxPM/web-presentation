"""文件功能：在独立配置与临时存储中离线导出 OpenAPI，不启动 lifespan 或连接业务服务。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def main() -> None:
    """清除应用环境覆盖并禁读 .env，导入应用后只序列化路由契约。"""

    from app.core import config

    setting_names = {name.upper() for name in config.AppSettings.model_fields}
    for name in list(os.environ):
        if name.upper() in setting_names:
            del os.environ[name]
    with tempfile.TemporaryDirectory(prefix="wp-openapi-") as directory:
        settings = config.AppSettings(
            _env_file=None,
            database_url="sqlite+aiosqlite:///:memory:",
            redis_url="memory://openapi-export",
            page_screenshot_local_root=str(Path(directory) / "storage"),
        )
        # 导入 main 前替换惰性配置入口，避免其全局 app 读取本机配置和挂载业务目录。
        config.get_settings = lambda: settings
        from app.main import app

        print(json.dumps(app.openapi(), ensure_ascii=False))


if __name__ == "__main__":
    main()

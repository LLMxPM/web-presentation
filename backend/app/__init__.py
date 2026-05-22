"""文件功能：导出后台服务包的公开入口。"""

from app.main import create_app, main

__all__ = ["create_app", "main"]

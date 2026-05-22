"""文件功能：导出 SQLAlchemy 基础元数据对象，统一管理模型注册。"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 ORM 模型的统一基类。"""

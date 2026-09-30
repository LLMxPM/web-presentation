"""文件功能：保存普通 AI Run 执行进程的实例身份与存活租约，不恢复模型执行。"""

from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class AiAgentProcessOwner(Base):
    """每个进程实例一个 owner；UUID 区分容器重建与 PID 重用。"""

    __tablename__ = "ai_agent_process_owners"

    owner_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    heartbeat_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)

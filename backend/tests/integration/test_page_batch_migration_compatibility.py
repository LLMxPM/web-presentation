"""文件功能：验证删列后前向补偿迁移能恢复 N-1 页面 Batch 的完整 ORM 读写。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from app.models.ai_page_mutation import AiPageMutationBatch
from sqlalchemy import Column, Integer, MetaData, create_engine, inspect, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, registry


def _migrate(path: Path, revision: str, *, command: str = "upgrade") -> None:
    """在独立临时库执行真实迁移，不读取开发数据库。"""

    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{path.as_posix()}", "REDIS_URL": "memory://batch-compat"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", command, revision],
        cwd=Path(__file__).resolve().parents[2], env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def _legacy_batch_model() -> type:
    """重建 4c7eee8 的完整 Batch 映射：当前同名字段加旧 lease_generation。"""

    metadata = MetaData()
    # 同时复制外键目标，完整 ORM flush 需要解析父表；不会在数据库建表。
    for source_table in AiPageMutationBatch.metadata.tables.values():
        source_table.to_metadata(metadata)
    table = metadata.tables["ai_page_mutation_batches"]
    table.append_column(Column("lease_generation", Integer, nullable=False, default=0))

    class LegacyBatch:
        """冻结旧列集合，确保 SELECT 与 INSERT 不只测试手写字段子集。"""

    registry().map_imperatively(LegacyBatch, table)
    return LegacyBatch


def test_forward_migration_restores_legacy_orm_and_current_insert(tmp_path: Path) -> None:
    """已经删列的库前滚后，历史行、旧完整读写和当前省略字段写入均可用。"""

    path = tmp_path / "compat.db"
    _migrate(path, "20260930_0100")
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        assert "lease_generation" not in {c["name"] for c in inspect(engine).get_columns("ai_page_mutation_batches")}
        legacy = _legacy_batch_model()
        with Session(engine) as session, pytest.raises(OperationalError, match="lease_generation"):
            session.scalars(select(legacy)).all()
        with Session(engine) as session:
            session.add(AiPageMutationBatch(batch_id="before", run_id="run", session_id="session", run_step=1))
            session.commit()
        _migrate(path, "20260930_0200")
        with Session(engine) as session:
            assert session.scalar(select(legacy).where(legacy.batch_id == "before")).lease_generation == 0
            session.add(legacy(batch_id="old", run_id="run", session_id="session", run_step=2, status="pending"))
            session.add(AiPageMutationBatch(batch_id="new", run_id="run", session_id="session", run_step=3))
            session.commit()
            old = session.scalar(select(legacy).where(legacy.batch_id == "old"))
            old.lease_generation += 1
            old.status = "completed"
            session.commit()
            session.expire_all()
            assert session.scalar(select(legacy).where(legacy.batch_id == "old")).lease_generation == 1
            assert session.scalar(select(legacy).where(legacy.batch_id == "new")).lease_generation == 0
            assert session.scalar(select(AiPageMutationBatch).where(AiPageMutationBatch.batch_id == "old")).status == "completed"
    finally:
        engine.dispose()


def test_compensation_migration_round_trip_keeps_batch_rows(tmp_path: Path) -> None:
    """补偿迁移可往返到删列版本；应用回滚应保留补偿 schema，历史行不会丢失。"""

    path = tmp_path / "round-trip.db"
    _migrate(path, "20260930_0200")
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        with Session(engine) as session:
            session.add(AiPageMutationBatch(batch_id="keep", run_id="run", session_id="session", run_step=1))
            session.commit()
        _migrate(path, "20260930_0100", command="downgrade")
        _migrate(path, "20260930_0200")
        with Session(engine) as session:
            assert session.get(AiPageMutationBatch, "keep") is not None
    finally:
        engine.dispose()

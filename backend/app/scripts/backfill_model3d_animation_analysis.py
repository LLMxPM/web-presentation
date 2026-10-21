"""文件功能：按需回填三维资源动作分析摘要，默认只读预览，显式 --apply 才写库。

只处理 model3d、活动且非历史资源；按 workflow 规定的批次上限读取文件，
不把动作分析放入资源列表查询，也不解码整条动画轨道。
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.asset import WorkspaceAsset
from app.models.enums import AssetType, RecordStatus
from app.scripts.diagnose_ai_run import load_backend_env_for_cli
from app.services.asset_service import AssetService
from app.services.model3d_glb_service import ANIMATION_ANALYSIS_VERSION, Model3dGlbService


async def backfill_model3d_animation_analysis(
    *,
    workspace_id: int | None,
    limit: int,
    apply: bool,
) -> dict[str, Any]:
    """扫描指定批次内的三维资源并回填动作摘要；返回有界候选与失败摘要。"""

    normalized_limit = max(1, min(int(limit), 200))
    async with get_session_factory()() as session:
        service = AssetService(session)
        statement = (
            select(WorkspaceAsset)
            .where(
                WorkspaceAsset.asset_type == AssetType.MODEL3D.value,
                WorkspaceAsset.status == RecordStatus.ACTIVE.value,
                WorkspaceAsset.history_kind.is_(None),
            )
            .order_by(WorkspaceAsset.workspace_id.asc(), WorkspaceAsset.id.asc())
            .limit(normalized_limit)
        )
        if workspace_id is not None:
            statement = statement.where(WorkspaceAsset.workspace_id == workspace_id)
        assets = list((await session.execute(statement)).scalars().all())

        candidates: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        skipped_current = 0
        for asset in assets:
            metadata = dict(asset.analysis_metadata or {})
            model3d = metadata.get("model3d") if isinstance(metadata.get("model3d"), dict) else {}
            if int(model3d.get("animation_analysis_version") or 0) >= ANIMATION_ANALYSIS_VERSION:
                skipped_current += 1
                continue
            try:
                content = await service.driver.read_content(asset.workspace_id, asset.file_name)
                summary = Model3dGlbService.analyze(content)
            except Exception as error:  # noqa: BLE001
                failures.append(_failure(asset, error))
                continue
            next_metadata = {
                "schema_version": 1,
                "kind": "model3d",
                "model3d": summary,
            }
            candidates.append(_candidate(asset, summary))
            if apply:
                asset.analysis_metadata = next_metadata
        if apply and candidates:
            await session.commit()
        return {
            "apply": apply,
            "workspace_id": workspace_id,
            "limit": normalized_limit,
            "scanned_count": len(assets),
            "skipped_current_count": skipped_current,
            "candidate_count": len(candidates),
            "failure_count": len(failures),
            "candidates": candidates,
            "failures": failures,
        }


def _candidate(asset: WorkspaceAsset, summary: dict[str, Any]) -> dict[str, Any]:
    """读取候选摘要，不输出资源内容或本地路径。"""

    animations = summary.get("animations") or []
    return {
        "asset_id": asset.id,
        "workspace_id": asset.workspace_id,
        "name": asset.name,
        "animation_count": len(animations),
        "supported_animation_count": sum(1 for item in animations if item.get("supported")),
        "animation_analysis_version": summary.get("animation_analysis_version"),
    }


def _failure(asset: WorkspaceAsset, error: Exception) -> dict[str, Any]:
    """输出有界失败摘要，避免异常细节无限增长。"""

    message = str(error).strip()
    return {
        "asset_id": asset.id,
        "workspace_id": asset.workspace_id,
        "name": asset.name,
        "error": message[:220],
    }


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""

    parser = argparse.ArgumentParser(description="回填三维资源动作分析摘要，默认只输出 dry-run 结果。")
    parser.add_argument("--workspace-id", type=int, help="只扫描指定工作空间。")
    parser.add_argument("--limit", type=int, default=50, help="本批次最多扫描的资源数，范围 1–200，默认 50。")
    parser.add_argument("--apply", action="store_true", help="实际写入数据库；不传时只预览。")
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    """CLI 异步入口。"""

    args = build_parser().parse_args(argv)
    load_backend_env_for_cli()
    payload = await backfill_model3d_animation_analysis(
        workspace_id=args.workspace_id,
        limit=args.limit,
        apply=args.apply,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> None:
    """CLI 同步入口。"""

    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()

"""文件功能：按需回填工作空间资源近似比例元数据，默认只读预览，显式 --apply 才写库。"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.asset import WorkspaceAsset
from app.models.enums import AssetType
from app.scripts.diagnose_ai_run import load_backend_env_for_cli
from app.services.asset_render_metadata_service import AssetRenderMetadataService
from app.services.asset_service import AssetService


async def backfill_asset_render_hints(*, workspace_id: int | None, apply: bool) -> dict[str, Any]:
    """扫描资源并回填自动比例；默认 dry-run 不写入数据库。"""

    async with get_session_factory()() as session:
        service = AssetService(session)
        statement = select(WorkspaceAsset).order_by(WorkspaceAsset.workspace_id.asc(), WorkspaceAsset.id.asc())
        if workspace_id is not None:
            statement = statement.where(WorkspaceAsset.workspace_id == workspace_id)
        assets = list((await session.execute(statement)).scalars().all())
        candidates: list[dict[str, Any]] = []
        skipped_manual = 0
        for asset in assets:
            if AssetRenderMetadataService.is_manual_metadata(asset.render_metadata):
                skipped_manual += 1
                continue
            try:
                content = await service.driver.read_content(asset.workspace_id, asset.file_name)
                next_metadata = AssetRenderMetadataService.build_auto_metadata(
                    AssetType(asset.asset_type),
                    asset.original_name,
                    asset.content_type,
                    content,
                )
            except Exception as error:  # noqa: BLE001
                candidates.append(_dump_candidate(asset, error=str(error)))
                continue
            if next_metadata == asset.render_metadata:
                continue
            candidates.append(_dump_candidate(asset, next_metadata=next_metadata))
            if apply:
                asset.render_metadata = next_metadata
        if apply:
            await session.commit()
        return {
            "apply": apply,
            "workspace_id": workspace_id,
            "scanned_count": len(assets),
            "skipped_manual_count": skipped_manual,
            "candidate_count": len(candidates),
            "candidates": candidates,
        }


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""

    parser = argparse.ArgumentParser(description="回填资源近似比例 render_metadata，默认只输出 dry-run 结果。")
    parser.add_argument("--workspace-id", type=int, help="只扫描指定工作空间。")
    parser.add_argument("--apply", action="store_true", help="实际写入数据库；不传时只预览。")
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    """CLI 异步入口。"""

    args = build_parser().parse_args(argv)
    load_backend_env_for_cli()
    payload = await backfill_asset_render_hints(workspace_id=args.workspace_id, apply=args.apply)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


def _dump_candidate(
    asset: WorkspaceAsset,
    *,
    next_metadata: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """生成单个待处理资源的摘要，避免输出资源内容。"""

    return {
        "asset_id": asset.id,
        "workspace_id": asset.workspace_id,
        "name": asset.name,
        "asset_type": asset.asset_type,
        "current_render_metadata": asset.render_metadata,
        "next_render_metadata": next_metadata,
        "error": error,
    }


def main() -> None:
    """CLI 同步入口。"""

    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()

"""文件功能：只读诊断页面截图新鲜度判定，按输入层归因“页面被判为旧截图”的真实原因。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import utc_now
from app.db.session import get_session_factory
from app.models.enums import PageFileType, RecordStatus
from app.models.font import WorkspaceFontConfig
from app.models.page import Page
from app.models.page_screenshot_job import PageScreenshotJob
from app.models.workspace import Project
from app.scripts.diagnose_ai_run import load_backend_env_for_cli
from app.services import runtime_release_identity
from app.services.capture_viewport_resolver import CaptureViewportResolver
from app.services.page_screenshot_fingerprint_service import (
    PageScreenshotConfigSnapshot,
    PageScreenshotFingerprintService,
)

OutputFormat = Literal["summary", "json"]
HASH_PREFIX = 12


def _short(value: object) -> str:
    """截断 hash 便于阅读；空值输出占位符。"""

    text = str(value or "").strip()
    return text[:HASH_PREFIX] if text else "-"


def _iso(value: datetime | None) -> str | None:
    """把时间列转为 ISO 字符串，便于 JSON 输出。"""

    return value.isoformat() if isinstance(value, datetime) else None


def _read_error_label(error: BaseException) -> str:
    """把重算异常归类，区分业务缺失与基础设施失败。"""

    from app.core.exceptions import AppException

    if isinstance(error, AppException):
        return f"read_failed:{error.code}"
    return f"read_failed:{type(error).__name__}"


async def _list_target_pages(
    session: AsyncSession,
    *,
    workspace_id: int | None,
    project_id: int | None,
    page_id: int | None,
    limit: int,
) -> list[Page]:
    """按工作空间/项目/页面收敛诊断范围，只取支持截图的未删除 Vue 页面。"""

    stmt = select(Page).where(Page.deleted_at.is_(None), Page.file_type == PageFileType.VUE.value)
    if page_id is not None:
        stmt = stmt.where(Page.id == page_id)
    if project_id is not None:
        stmt = stmt.where(Page.project_id == project_id)
    if workspace_id is not None:
        stmt = stmt.where(Page.workspace_id == workspace_id)
    rows = (
        await session.execute(stmt.order_by(Page.project_id.asc().nullsfirst(), Page.id.asc()))
    ).scalars().all()
    return list(rows[: max(1, limit)])


async def _resolve_workspace_id(
    session: AsyncSession,
    *,
    workspace_id: int | None,
    project_id: int | None,
    page_id: int | None,
) -> int | None:
    """未显式指定工作空间时，从项目或页面反推工作空间，供字体审计使用。"""

    if workspace_id is not None:
        return workspace_id
    if project_id is not None:
        return await session.scalar(select(Project.workspace_id).where(Project.id == project_id))
    if page_id is not None:
        return await session.scalar(select(Page.workspace_id).where(Page.id == page_id))
    return None


async def _recompute_snapshot(session: AsyncSession, page: Page) -> PageScreenshotConfigSnapshot:
    """用生产同一入口重算页面截图指纹，不在诊断侧复制 hash 公式。"""

    return await PageScreenshotFingerprintService(session).build_page_snapshot(page)


def _classify_bucket(
    page: Page,
    *,
    recomputed_hash: str | None,
    viewport: tuple[int, int] | None,
    read_error: str | None,
) -> tuple[str, str]:
    """给出稳定判定桶与可读原因，把“读取失败”与“确实过期”分开。"""

    if not page.screenshot_storage_key:
        return "no_screenshot", "尚无截图指针"
    if read_error:
        return read_error, "指纹重算失败；列表页会把它折算成旧截图"
    if page.screenshot_version_no is None or int(page.screenshot_version_no) != int(page.current_version_no):
        return "version_mismatch", f"截图版本 {page.screenshot_version_no} != 当前 {page.current_version_no}"
    if viewport is not None and (
        int(page.screenshot_viewport_width or 0) != viewport[0]
        or int(page.screenshot_viewport_height or 0) != viewport[1]
    ):
        return (
            "viewport_mismatch",
            f"视口 {page.screenshot_viewport_width}x{page.screenshot_viewport_height} != {viewport[0]}x{viewport[1]}",
        )
    if str(page.screenshot_config_hash or "") != str(recomputed_hash or ""):
        return "hash_mismatch", "持久化 config_hash 与当前重算不一致"
    return "fresh", "判定为最新"


async def _sweep_runtime_identity(
    session: AsyncSession,
    page: Page,
    candidates: list[str],
) -> dict[str, str]:
    """把 Runtime 发布身份逐个设为候选值后重算，找出能复现持久化 hash 的那个。"""

    original = runtime_release_identity._identity
    results: dict[str, str] = {}
    try:
        for value in candidates:
            runtime_release_identity._identity = value
            results[value] = (await _recompute_snapshot(session, page)).config_hash
    finally:
        runtime_release_identity._identity = original
    return results


async def _project_theme_text(session: AsyncSession, page: Page) -> str:
    """读取项目自身主题文本，供指纹重算失败时的字体引用审计使用。"""

    if page.project_id is None:
        return ""
    project = await session.get(Project, page.project_id)
    return str(project.theme_config_yaml or "") if project is not None else ""


async def _font_audit(session: AsyncSession, page: Page, haystack: str) -> dict[str, Any]:
    """登记工作空间字体行与页面/主题实际引用的字体，核对「未引用字体不进身份」的口径是否成立。

    截图身份现在只收 Runtime 字体包真正下发的字体族（主题 typography + 源码显式声明），
    因此这里的 ``unreferenced_rows`` 只是登记信息，不再代表串扰面；若某页仍因未引用字体被判过期，
    说明该过滤口径失效，应回到 ``CodeCheckFingerprintBuilder._referenced_font_configs`` 排查。
    """

    rows = (
        await session.execute(
            select(WorkspaceFontConfig)
            .where(WorkspaceFontConfig.workspace_id == page.workspace_id)
            .where(WorkspaceFontConfig.status == RecordStatus.ACTIVE.value)
            .order_by(WorkspaceFontConfig.asset_name.asc())
        )
    ).scalars().all()
    registered = [f"{row.font_family}/{row.asset_name}" for row in rows]
    referenced = [
        signature
        for row, signature in zip(rows, registered)
        if (row.font_family and row.font_family in haystack) or (row.asset_name and row.asset_name in haystack)
    ]
    return {
        "workspace_font_rows": len(rows),
        "registered_rows": registered,
        "actually_referenced": referenced,
        "unreferenced_rows": [item for item in registered if item not in referenced],
    }


async def _job_timeline(session: AsyncSession, page_id: int, limit: int) -> list[dict[str, Any]]:
    """读取该页面最近的截图任务，作为 config_hash 的历史时间序列。"""

    rows = (
        await session.execute(
            select(PageScreenshotJob)
            .where(PageScreenshotJob.page_id == page_id)
            .order_by(PageScreenshotJob.created_at.desc(), PageScreenshotJob.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "job_id": int(job.id),
            "created_at": _iso(job.created_at),
            "source": job.source,
            "status": job.status,
            "error_code": job.error_code,
            "target_page_version_no": int(job.target_page_version_no),
            "config_hash": job.config_hash,
            "viewport": f"{job.viewport_width}x{job.viewport_height}",
        }
        for job in rows
    ]


def _hash_drift(jobs: list[dict[str, Any]]) -> dict[str, list[str]]:
    """同一入队页面版本出现多个 config_hash。

    只有时间上相邻、且都产生于当前指纹公式之后的多个 hash 才是「内容未变却漂移」的直接证据；
    截图身份公式调整（例如将 Runtime 发布构建移出截图身份）前后的历史任务本来就会不同，
    不能跨变更边界当作漂移。
    """

    by_version: dict[int, list[str]] = {}
    for job in jobs:
        versions = by_version.setdefault(int(job["target_page_version_no"]), [])
        if job["config_hash"] not in versions:
            versions.append(job["config_hash"])
    return {str(key): [_short(value) for value in values] for key, values in by_version.items() if len(values) > 1}


async def diagnose_page(session: AsyncSession, page: Page, candidates: list[str]) -> dict[str, Any]:
    """收集单页截图新鲜度证据：判定桶、身份候选扫描、字体串扰与任务历史。"""

    item: dict[str, Any] = {
        "page_id": int(page.id),
        "page_code": page.code,
        "title": page.title,
        "workspace_id": page.workspace_id,
        "project_id": page.project_id,
        "current_version_no": int(page.current_version_no),
        "screenshot_version_no": page.screenshot_version_no,
        "screenshot_config_hash": page.screenshot_config_hash,
        "screenshot_viewport": f"{page.screenshot_viewport_width}x{page.screenshot_viewport_height}",
        "screenshot_updated_at": _iso(page.screenshot_updated_at),
    }

    read_error: str | None = None
    base_snapshot: PageScreenshotConfigSnapshot | None = None
    snapshot: PageScreenshotConfigSnapshot | None = None
    viewport: tuple[int, int] | None = None
    try:
        service = PageScreenshotFingerprintService(session)
        base_snapshot = await service.build_page_base_snapshot(page)
        snapshot = await service.build_page_snapshot(page)
        resolved = CaptureViewportResolver().resolve(page, project_page_config=snapshot.page_config)
        viewport = (resolved.width, resolved.height)
    except Exception as error:  # noqa: BLE001 - 诊断要把失败作为证据输出而不是抛出
        read_error = _read_error_label(error)

    bucket, reason = _classify_bucket(
        page,
        recomputed_hash=snapshot.config_hash if snapshot else None,
        viewport=viewport,
        read_error=read_error,
    )
    item.update(
        {
            "bucket": bucket,
            "reason": reason,
            "read_error": read_error,
            "recomputed_hash_live": snapshot.config_hash if snapshot else None,
            "project_layer_hash": base_snapshot.config_hash if base_snapshot else None,
            "theme_key": base_snapshot.theme_key if base_snapshot else None,
            "viewport_now": f"{viewport[0]}x{viewport[1]}" if viewport else None,
        }
    )

    if bucket == "hash_mismatch":
        try:
            sweep = await _sweep_runtime_identity(session, page, candidates)
            matched = [value for value, digest in sweep.items() if digest == page.screenshot_config_hash]
            item["runtime_identity_sweep"] = {
                value: {"hash": _short(digest), "matches_stored": digest == page.screenshot_config_hash}
                for value, digest in sweep.items()
            }
            item["runtime_verdict"] = (
                f"stored 仅由 runtime_build={matched[0]} 复现（其他输入完全相同）"
                if matched
                else "无候选可复现 stored，差异在其他输入层"
            )
        except Exception as error:  # noqa: BLE001
            item["runtime_identity_sweep"] = {}
            item["runtime_verdict"] = f"sweep_failed:{type(error).__name__}"

    if page.workspace_id is not None:
        # 指纹重算失败时也要能审计字体串扰面，因此回退到项目自身主题文本。
        theme_text = (
            json.dumps(snapshot.theme_config or {}, default=str)
            if snapshot is not None
            else await _project_theme_text(session, page)
        )
        item["font_audit"] = await _font_audit(session, page, "\n".join([page.page_content or "", theme_text]))

    item["jobs"] = await _job_timeline(session, int(page.id), 8)
    item["same_version_multiple_hashes"] = _hash_drift(item["jobs"])
    return item


def _aggregate(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """汇总判定桶、身份扫描结论与串扰指标。"""

    by_project: dict[str, dict[str, int]] = {}
    for page in pages:
        key = f"project/{page['project_id'] if page['project_id'] is not None else '-'}"
        slot = by_project.setdefault(key, {"pages": 0, "fresh": 0, "hash_mismatch": 0, "read_failed": 0, "other": 0})
        slot["pages"] += 1
        bucket = str(page["bucket"])
        if bucket == "fresh":
            slot["fresh"] += 1
        elif bucket == "hash_mismatch":
            slot["hash_mismatch"] += 1
        elif bucket.startswith("read_failed"):
            slot["read_failed"] += 1
        else:
            slot["other"] += 1
    return {
        "total_pages": len(pages),
        "buckets": dict(Counter(str(page["bucket"]) for page in pages)),
        "runtime_verdicts": dict(
            Counter(str(page["runtime_verdict"]) for page in pages if page.get("runtime_verdict"))
        ),
        "drift_pages": [
            {"page_id": page["page_id"], "same_version_multiple_hashes": page["same_version_multiple_hashes"]}
            for page in pages
            if page["same_version_multiple_hashes"]
        ],
        "unreferenced_font_pages": [
            {
                "page_id": page["page_id"],
                "workspace_font_rows": page["font_audit"]["workspace_font_rows"],
                "unreferenced_count": len(page["font_audit"]["unreferenced_rows"]),
            }
            for page in pages
            if page.get("font_audit", {}).get("unreferenced_rows")
        ],
        "by_project": by_project,
    }


def _render_pages_detail(pages: list[dict[str, Any]]) -> list[str]:
    """渲染非最新页面的逐页证据。"""

    interesting = [page for page in pages if page["bucket"] not in {"fresh", "no_screenshot"}]
    lines = ["", f"明细（非最新且已排除无截图页面 {len(interesting)} 个）:"]
    for page in interesting:
        audit = page.get("font_audit") or {}
        lines.extend(
            [
                "",
                f"* page {page['page_id']} {page['page_code']}「{page['title']}」 project={page['project_id'] or '-'}",
                f"  bucket={page['bucket']} reason={page['reason']}",
                (
                    f"  stored={_short(page['screenshot_config_hash'])} recomputed(live)={_short(page['recomputed_hash_live'])} "
                    f"项目层={_short(page['project_layer_hash'])} 主题={page['theme_key'] or '-'}"
                ),
                (
                    f"  版本 {page['screenshot_version_no']}->{page['current_version_no']} "
                    f"视口 {page['screenshot_viewport']} (现算 {page['viewport_now'] or '-'}) 截图时间={page['screenshot_updated_at'] or '-'}"
                ),
            ]
        )
        sweep = page.get("runtime_identity_sweep") or {}
        if sweep:
            lines.append(
                "  身份扫描: "
                + " | ".join(
                    f"{value} -> {entry['hash']}{'' if entry['matches_stored'] else ' 不匹配'}"
                    for value, entry in sweep.items()
                )
            )
            lines.append(f"  结论: {page.get('runtime_verdict')}")
        if audit:
            lines.append(
                f"  字体层: 工作空间 ACTIVE 行 {audit['workspace_font_rows']} / 页面或主题引用 {len(audit['actually_referenced'])}"
                f" / 未引用（不进截图身份）{len(audit['unreferenced_rows'])}"
            )
        if page["same_version_multiple_hashes"]:
            lines.append(f"  hash 漂移（同版本多指纹）: {page['same_version_multiple_hashes']}")
        if page["jobs"]:
            lines.append(
                "  任务历史: "
                + "; ".join(
                    f"#{job['job_id']} {job['created_at']} {job['source']}/{job['status']}"
                    + (f"({job['error_code']})" if job["error_code"] else "")
                    + f" v{job['target_page_version_no']} {_short(job['config_hash'])}"
                    for job in page["jobs"][:5]
                )
            )
    return lines


def _render_summary(payload: dict[str, Any]) -> str:
    """渲染可读摘要，优先暴露判定桶分布与身份扫描结论。"""

    scope = payload["scope"]
    runtime = payload["runtime_identity"]
    overview = payload["overview"]
    verdicts = overview["runtime_verdicts"] or {"无 hash 不符页面": 0}
    lines = [
        "截图新鲜度诊断（只读，不修改任何数据）",
        (
            f"范围: workspace={scope['workspace_id'] or '-'} project={scope['project_id'] or '-'} "
            f"page={scope['page_id'] or '-'} 命中页面={overview['total_pages']}"
        ),
        f"运行时身份: 诊断进程初始={runtime['process_initial']} 实时探测={runtime['live_probe']} 扫描候选={runtime['candidates']}",
        "",
        "判定桶: " + " | ".join(f"{key}={value}" for key, value in sorted(overview["buckets"].items())),
        "身份扫描结论: " + " | ".join(f"{key} -> {value} 页" for key, value in verdicts.items()),
        "",
        (
            f"字体登记: 存在未被页面或主题引用的字体行的页面 {len(overview['unreferenced_font_pages'])} 个"
            f"（未引用行已不进截图身份，此数只作口径核对）；"
            f"同版本出现多个 config_hash 的页面 {len(overview['drift_pages'])} 个"
            "（任务历史可能跨指纹公式变更，需按时间切分判读）"
        ),
        "",
        "按项目分布:",
        *[
            f"- {name}: pages={slot['pages']} fresh={slot['fresh']} hash_mismatch={slot['hash_mismatch']} "
            f"read_failed={slot['read_failed']} other={slot['other']}"
            for name, slot in overview["by_project"].items()
        ],
    ]
    lines.extend(_render_pages_detail(payload["pages"]))
    return "\n".join(lines)


async def async_main(argv: list[str] | None = None) -> int:
    """CLI 异步入口：探测运行时身份、逐页收集证据并输出。"""

    args = _build_parser().parse_args(argv)
    load_backend_env_for_cli()

    initial_identity = runtime_release_identity._identity
    live_probe = "skipped(--no-probe)"
    if not args.no_probe:
        live_probe = await runtime_release_identity.refresh_runtime_release_identity()

    candidates: list[str] = []
    for value in [live_probe, initial_identity]:
        if value and value not in candidates:
            candidates.append(value)

    async with get_session_factory()() as session:
        workspace_id = await _resolve_workspace_id(
            session, workspace_id=args.workspace_id, project_id=args.project_id, page_id=args.page_id
        )
        pages = await _list_target_pages(
            session,
            workspace_id=workspace_id,
            project_id=args.project_id,
            page_id=args.page_id,
            limit=args.max_pages,
        )
        if not pages:
            print("未命中任何可诊断的 Vue 页面，请检查 --workspace-id/--project-id/--page-id。", file=sys.stderr)
            return 1
        items = [await diagnose_page(session, page, candidates) for page in pages]
        await session.rollback()

    payload = {
        "generated_at": utc_now().isoformat(),
        "scope": {"workspace_id": workspace_id, "project_id": args.project_id, "page_id": args.page_id},
        "runtime_identity": {
            "process_initial": initial_identity,
            "live_probe": live_probe,
            "candidates": candidates,
            "page_mutation_capture_screenshot": get_settings().page_mutation_capture_screenshot,
        },
        "overview": _aggregate(items),
        "pages": items,
    }
    content = (
        json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        if args.format == "json"
        else _render_summary(payload)
    )

    if args.output:
        path = Path(args.output)
        if path.parent != Path("."):
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{content}\n", encoding="utf-8")
        print(f"诊断输出已写入 {path}")
    else:
        print(content)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """构建只读诊断 CLI 参数。"""

    parser = argparse.ArgumentParser(description="只读诊断页面截图新鲜度判定，按输入层归因旧截图。")
    parser.add_argument("--workspace-id", type=int, help="按工作空间收敛诊断范围。")
    parser.add_argument("--project-id", type=int, help="按项目收敛诊断范围。")
    parser.add_argument("--page-id", type=int, help="只诊断单个页面。")
    parser.add_argument("--max-pages", type=int, default=25, help="最多诊断页面数，默认 25。")
    parser.add_argument("--no-probe", action="store_true", help="跳过 Runtime /__runtime_healthz 实时探测。")
    parser.add_argument("--format", choices=("summary", "json"), default="summary", help="输出格式。")
    parser.add_argument("--output", help="输出文件路径；未指定时输出到 stdout。")
    return parser


def main() -> None:
    """CLI 同步入口。"""

    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()

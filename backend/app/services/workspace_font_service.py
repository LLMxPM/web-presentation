"""文件功能：管理工作空间字体族与字体文件（face）、主题字体引用解析与源码字体声明解析。"""

from collections.abc import Iterable
from pathlib import Path
import re

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.models.asset import WorkspaceAsset
from app.models.enums import AssetType, RecordStatus
from app.models.font import WorkspaceFontConfig, WorkspaceFontFamily
from app.models.workspace import Project
from app.schemas.asset import AssetFontConfigSummary
from app.schemas.common import ListQuery, PagedResponse
from app.schemas.font import (
    FontBundleResponse,
    WorkspaceFontConfigCreateRequest,
    WorkspaceFontConfigResponse,
    WorkspaceFontConfigUpdateRequest,
    WorkspaceFontFamilyResponse,
    WorkspaceFontFamilyUpdateRequest,
)
from app.services.workspace_theme_service import WorkspaceThemeService


FONT_ASSET_CALL_PATTERN = re.compile(
    r"\b(?:useAssetFontFamily|resolveAssetFontFamily)\s*\(\s*(?:'(?P<single>(?:\\.|[^'\\])*)'|\"(?P<double>(?:\\.|[^\"\\])*)\")",
    flags=re.DOTALL,
)

# @font-face 字段白名单校验，防止脏数据直接注入 Runtime 生成的 CSS。
FONT_WEIGHT_VALUE_PATTERN = re.compile(r"^\d{1,4}$")
FONT_WEIGHT_RANGE_PATTERN = re.compile(r"^(\d{1,4}) (\d{1,4})$")
FONT_STYLE_ALLOWED_VALUES = {"normal", "italic", "oblique"}
FONT_DISPLAY_ALLOWED_VALUES = {"auto", "block", "swap", "fallback", "optional"}


class WorkspaceFontService:
    """负责工作空间字体族与字体文件 CRUD、主题引用解析与字体资产保护。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workspace_theme_service = WorkspaceThemeService(session)

    async def list_workspace_fonts(
        self,
        workspace_id: int,
        query: ListQuery,
    ) -> PagedResponse[WorkspaceFontConfigResponse]:
        """按分页条件返回指定工作空间下的字体配置。"""

        font_configs, total = await self._list_font_configs_page(workspace_id, query)
        asset_map = await self._get_asset_map_by_ids(workspace_id, [item.asset_id for item in font_configs])
        responses = [self._to_response(item) for item in font_configs]
        for response in responses:
            asset = asset_map.get(response.asset_id)
            response.asset_url = self._build_asset_url(workspace_id, asset.file_hash) if asset else None
        return PagedResponse[WorkspaceFontConfigResponse](
            items=responses,
            total=total,
            page=query.page,
            page_size=query.page_size,
        )

    async def create_workspace_font(
        self,
        workspace_id: int,
        payload: WorkspaceFontConfigCreateRequest,
    ) -> WorkspaceFontConfigResponse:
        """创建新的工作空间字体配置。"""

        asset = await self._get_font_asset_or_raise(workspace_id, payload.asset_id)
        await self._ensure_asset_not_registered(workspace_id, asset.id)
        await self._ensure_asset_name_not_registered(workspace_id, asset.name)
        family = await self._get_or_create_family(workspace_id, payload.family_name)
        font_weight = self._normalize_font_weight(payload.font_weight)
        font_style = self._normalize_font_style(payload.font_style)
        await self._ensure_font_face_signature_available(
            family,
            font_weight=font_weight,
            font_style=font_style,
        )

        font_config = WorkspaceFontConfig(
            workspace_id=workspace_id,
            family=family,
            asset_id=asset.id,
            asset_name=asset.name,
            font_format=self._normalize_font_format(payload.font_format or self._infer_font_format(asset.original_name)),
            font_weight=font_weight,
            font_style=font_style,
            font_display=self._normalize_font_display(payload.font_display),
            status=payload.status.value,
        )
        self.session.add(font_config)
        await self.session.commit()
        await self.session.refresh(font_config)
        response = self._to_response(font_config)
        response.asset_url = self._build_asset_url(workspace_id, asset.file_hash)
        return response

    async def update_workspace_font(
        self,
        workspace_id: int,
        font_id: int,
        payload: WorkspaceFontConfigUpdateRequest,
    ) -> WorkspaceFontConfigResponse:
        """更新已有字体配置；修改 family_name 时把 face 移动到目标字体族（不存在时自动创建）。"""

        font_config = await self._get_font_config_or_raise(workspace_id, font_id)
        previous_family = font_config.family
        target_family = previous_family
        if payload.family_name is not None:
            target_family = await self._get_or_create_family(workspace_id, payload.family_name)
        next_font_weight = self._normalize_font_weight(payload.font_weight) if payload.font_weight is not None else font_config.font_weight
        next_font_style = self._normalize_font_style(payload.font_style) if payload.font_style is not None else font_config.font_style
        await self._ensure_font_face_signature_available(
            target_family,
            font_weight=next_font_weight,
            font_style=next_font_style,
            exclude_font_config_id=font_config.id,
        )
        family_changed = target_family.id != previous_family.id
        if family_changed:
            font_config.family = target_family
        if payload.font_format is not None:
            font_config.font_format = self._normalize_font_format(payload.font_format)
        if payload.font_weight is not None:
            font_config.font_weight = next_font_weight
        if payload.font_style is not None:
            font_config.font_style = next_font_style
        if payload.font_display is not None:
            font_config.font_display = self._normalize_font_display(payload.font_display)
        if payload.status is not None:
            font_config.status = payload.status.value

        if family_changed:
            await self.session.flush()
            await self._cleanup_family_if_orphan(workspace_id, previous_family)
        await self.session.commit()
        await self.session.refresh(font_config)
        asset = await self._get_font_asset_or_raise(workspace_id, font_config.asset_id)
        response = self._to_response(font_config)
        response.asset_url = self._build_asset_url(workspace_id, asset.file_hash)
        return response

    async def delete_workspace_font(self, workspace_id: int, font_id: int) -> None:
        """删除字体配置；若所属字体族仍被主题引用且这是最后一个 face 则拒绝；删除后空族级联清理。"""

        font_config = await self._get_font_config_or_raise(workspace_id, font_id)
        family = font_config.family
        conflict_error = self._build_font_config_in_use_error(font_config)
        if await self._is_font_config_referenced(workspace_id, font_config):
            raise conflict_error

        await self.session.delete(font_config)
        await self.session.flush()
        await self._cleanup_family_if_orphan(workspace_id, family)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise conflict_error from exc

    async def list_workspace_font_families(
        self,
        workspace_id: int,
        query: ListQuery,
    ) -> PagedResponse[WorkspaceFontFamilyResponse]:
        """分页返回工作空间字体族列表，每项内嵌该族全部字体文件（face）。"""

        stmt = select(WorkspaceFontFamily).where(WorkspaceFontFamily.workspace_id == workspace_id)
        count_stmt = select(func.count(WorkspaceFontFamily.id)).where(WorkspaceFontFamily.workspace_id == workspace_id)

        normalized_keyword = str(query.keyword or "").strip()
        if normalized_keyword:
            like_keyword = f"%{normalized_keyword}%"
            stmt = stmt.where(WorkspaceFontFamily.name.ilike(like_keyword))
            count_stmt = count_stmt.where(WorkspaceFontFamily.name.ilike(like_keyword))

        sort_column = getattr(WorkspaceFontFamily, query.sort_by, None)
        if sort_column is None or not hasattr(sort_column, "asc"):
            sort_column = WorkspaceFontFamily.updated_at
        sort_expression = sort_column.asc() if query.sort_order == "asc" else sort_column.desc()
        stmt = (
            stmt
            .order_by(sort_expression, WorkspaceFontFamily.id.desc())
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        total = int(await self.session.scalar(count_stmt) or 0)
        families = list((await self.session.execute(stmt)).scalars().all())
        return PagedResponse[WorkspaceFontFamilyResponse](
            items=await self._to_family_responses(workspace_id, families),
            total=total,
            page=query.page,
            page_size=query.page_size,
        )

    async def rename_font_family(
        self,
        workspace_id: int,
        family_id: int,
        payload: WorkspaceFontFamilyUpdateRequest,
    ) -> WorkspaceFontFamilyResponse:
        """重命名字体族，名称在工作空间内唯一（trim + 忽略大小写）。"""

        family = await self._get_family_or_raise(workspace_id, family_id)
        next_name = payload.name.strip()
        await self._ensure_family_name_available(workspace_id, next_name, exclude_family_id=family.id)
        family.name = next_name
        await self.session.commit()
        await self.session.refresh(family)
        return (await self._to_family_responses(workspace_id, [family]))[0]

    async def delete_font_family(self, workspace_id: int, family_id: int) -> None:
        """删除字体族；仍有 face 或被主题绑定时拒绝删除。"""

        family = await self._get_family_or_raise(workspace_id, family_id)
        face_count = int(
            await self.session.scalar(
                select(func.count(WorkspaceFontConfig.id)).where(WorkspaceFontConfig.family_id == family.id)
            )
            or 0
        )
        if face_count:
            raise AppException(
                status_code=409,
                code="FONT_FAMILY_NOT_EMPTY",
                detail=f'字体族 "{family.name}" 下仍有 {face_count} 个字体文件，请先删除或移出后再删除字体族。',
            )
        if await self.workspace_theme_service.is_font_referenced(workspace_id, family.id):
            raise AppException(
                status_code=409,
                code="FONT_FAMILY_IN_USE",
                detail=f'字体族 "{family.name}" 仍被主题引用，请先切换相关主题字体后再删除。',
            )
        await self.workspace_theme_service.purge_soft_deleted_theme_font_references(workspace_id, family.id)
        await self.session.delete(family)
        await self.session.commit()

    async def list_font_configs_for_family_ids(
        self,
        workspace_id: int,
        family_ids: Iterable[int],
    ) -> list[WorkspaceFontConfig]:
        """列出多个字体族下的全部字体文件，供导出打包收集依赖。"""

        normalized_ids = [family_id for family_id in dict.fromkeys(family_ids) if family_id is not None]
        if not normalized_ids:
            return []
        stmt = (
            select(WorkspaceFontConfig)
            .where(WorkspaceFontConfig.workspace_id == workspace_id)
            .where(WorkspaceFontConfig.family_id.in_(normalized_ids))
            .order_by(WorkspaceFontConfig.family_id.asc(), WorkspaceFontConfig.id.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_primary_font_config_for_family(
        self,
        workspace_id: int,
        family_id: int | None,
    ) -> WorkspaceFontConfig | None:
        """取字体族下最早注册的代表 face，供离线包主题字体引用序列化。"""

        if family_id is None:
            return None
        return await self.session.scalar(
            select(WorkspaceFontConfig)
            .where(WorkspaceFontConfig.workspace_id == workspace_id)
            .where(WorkspaceFontConfig.family_id == family_id)
            .order_by(WorkspaceFontConfig.id.asc())
            .limit(1)
        )

    async def register_imported_font_face(
        self,
        workspace_id: int,
        *,
        asset: WorkspaceAsset,
        font_family: str,
        font_format: str,
        font_weight: str,
        font_style: str,
        font_display: str,
        status: str,
    ) -> WorkspaceFontConfig:
        """按离线包载荷注册字体文件（get-or-create 字体族，不提交事务），供导入包服务复用。"""

        family = await self._get_or_create_family(workspace_id, font_family)
        normalized_weight = self._normalize_font_weight(font_weight)
        normalized_style = self._normalize_font_style(font_style)
        await self._ensure_font_face_signature_available(
            family,
            font_weight=normalized_weight,
            font_style=normalized_style,
        )
        font_config = WorkspaceFontConfig(
            workspace_id=workspace_id,
            family=family,
            asset_id=asset.id,
            asset_name=asset.name,
            font_format=self._normalize_font_format(font_format),
            font_weight=normalized_weight,
            font_style=normalized_style,
            font_display=self._normalize_font_display(font_display),
            status=status,
        )
        self.session.add(font_config)
        await self.session.flush()
        return font_config

    async def build_font_bundle_for_project(
        self,
        project: Project,
        *,
        explicit_asset_names: Iterable[str] | None = None,
    ) -> FontBundleResponse:
        """按项目主题实际引用解析需要下发给 runtime 的字体配置包。"""

        theme_key = str(project.theme_key or "").strip()
        theme_tokens = (
            await self.workspace_theme_service.get_theme_font_reference_tokens_by_key(
                project.workspace_id,
                theme_key,
            )
            if theme_key
            else []
        )
        return await self._build_font_bundle_for_references(
            project.workspace_id,
            theme_tokens=theme_tokens,
            explicit_asset_names=explicit_asset_names,
        )

    async def build_font_bundle_for_workspace(
        self,
        workspace_id: int,
        *,
        explicit_asset_names: Iterable[str] | None = None,
    ) -> FontBundleResponse:
        """按源码显式字体资源声明生成无主题预览字体包。"""

        return await self._build_font_bundle_for_references(
            workspace_id,
            theme_tokens=[],
            explicit_asset_names=explicit_asset_names,
        )

    async def build_font_bundle_for_theme_key(
        self,
        workspace_id: int,
        theme_key: str,
        *,
        explicit_asset_names: Iterable[str] | None = None,
    ) -> FontBundleResponse:
        """按单个主题 key 解析需要下发给 runtime 的字体配置包。"""

        theme_tokens = await self.workspace_theme_service.get_theme_font_reference_tokens_by_key(workspace_id, theme_key)
        return await self._build_font_bundle_for_references(
            workspace_id,
            theme_tokens=theme_tokens,
            explicit_asset_names=explicit_asset_names,
        )

    async def _build_font_bundle_for_references(
        self,
        workspace_id: int,
        *,
        theme_tokens: Iterable[str],
        explicit_asset_names: Iterable[str] | None = None,
    ) -> FontBundleResponse:
        """根据主题字体 token 与源码显式字体资源名合并生成运行时字体包。"""

        normalized_explicit_names = self._normalize_font_asset_names(explicit_asset_names or [])
        normalized_theme_tokens = [str(item or "").strip() for item in theme_tokens if str(item or "").strip()]
        if not normalized_theme_tokens and not normalized_explicit_names:
            return FontBundleResponse()

        font_configs = await self._list_font_configs(workspace_id, only_active=True)
        runtime_font_entries = await self._build_runtime_font_entries(workspace_id, font_configs)
        by_asset_name = self._build_font_entry_lookup_by_asset_name(runtime_font_entries)
        by_family_name = self._build_font_entry_lookup_by_family_name(runtime_font_entries)
        resolved_items: dict[str, dict[str, str]] = {}

        for token in normalized_theme_tokens:
            # 主题 token 为字体族名，命中后下发该族全部启用 face；兼容历史 asset_name token。
            for entry in by_family_name.get(token, []):
                self._append_runtime_font_item(resolved_items, entry)
            matched = by_asset_name.get(token)
            if matched:
                self._append_runtime_font_item(resolved_items, matched)

        missing_explicit_names: list[str] = []
        for asset_name in normalized_explicit_names:
            matched = by_asset_name.get(asset_name)
            if not matched:
                missing_explicit_names.append(asset_name)
                continue
            # 显式声明命中 face 后同样带上整个字体族，保证同族多字重可用。
            for entry in by_family_name.get(matched["font_family"], [matched]):
                self._append_runtime_font_item(resolved_items, entry)

        if missing_explicit_names:
            raise AppException(
                status_code=409,
                code="FONT_ASSET_NOT_REGISTERED",
                detail=f"页面源码声明了未注册或未启用的字体资源：{', '.join(missing_explicit_names)}。",
            )
        return FontBundleResponse(items=resolved_items)

    @staticmethod
    def collect_declared_font_asset_names_from_modules(modules_data: Iterable[dict[str, str]]) -> list[str]:
        """从模块源码列表中收集 Runtime Kit 字体资源静态声明。"""

        return WorkspaceFontService.collect_declared_font_asset_names(
            str(item.get("content") or "")
            for item in modules_data
        )

    @staticmethod
    def collect_declared_font_asset_names(sources: Iterable[str]) -> list[str]:
        """从 Vue/TS 源码中收集 useAssetFontFamily/resolveAssetFontFamily 的静态资源名。"""

        result: list[str] = []
        seen: set[str] = set()
        for source in sources:
            for match in FONT_ASSET_CALL_PATTERN.finditer(str(source or "")):
                raw_value = match.group("single") if match.group("single") is not None else match.group("double")
                normalized_name = WorkspaceFontService._normalize_font_asset_name(
                    WorkspaceFontService._unescape_js_string_literal(str(raw_value or ""))
                )
                if not normalized_name or normalized_name in seen:
                    continue
                seen.add(normalized_name)
                result.append(normalized_name)
        return result

    @staticmethod
    def _append_runtime_font_item(target: dict[str, dict[str, str]], item: dict[str, str]) -> None:
        """把运行时字体条目按 asset_name 写入字体包。"""

        target[item["asset_name"]] = {
            "asset_name": item["asset_name"],
            "font_family": item["font_family"],
            "font_format": item["font_format"],
            "font_weight": item["font_weight"],
            "font_style": item["font_style"],
            "font_display": item["font_display"],
        }

    @staticmethod
    def _normalize_font_asset_names(values: Iterable[str]) -> list[str]:
        """规范化并去重字体资源逻辑名。"""

        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = WorkspaceFontService._normalize_font_asset_name(value)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    @staticmethod
    def _normalize_font_asset_name(value: str) -> str:
        """按 Runtime 资源 key 规则规范化字体资源逻辑名。"""

        normalized = str(value or "").strip().replace("\\", "/").lstrip("./")
        if not normalized or re.match(r"^https?://", normalized, flags=re.IGNORECASE):
            return ""
        return normalized

    @staticmethod
    def _unescape_js_string_literal(value: str) -> str:
        """处理静态 JS 字符串字面量中的常见转义。"""

        return (
            str(value or "")
            .replace("\\'", "'")
            .replace('\\"', '"')
            .replace("\\\\", "\\")
        )

    @staticmethod
    def _build_font_entry_lookup_by_asset_name(
        runtime_font_entries: list[dict[str, str]],
    ) -> dict[str, dict[str, str]]:
        """按资产逻辑名建立字体条目索引，便于源码显式声明直接命中字体资源。"""

        return {
            entry["asset_name"]: entry
            for entry in runtime_font_entries
            if entry.get("asset_name")
        }

    @staticmethod
    def _build_font_entry_lookup_by_family_name(
        runtime_font_entries: list[dict[str, str]],
    ) -> dict[str, list[dict[str, str]]]:
        """按字体族名聚合字体条目，主题 token 命中后可整族下发。"""

        result: dict[str, list[dict[str, str]]] = {}
        for entry in runtime_font_entries:
            family_name = str(entry.get("font_family") or "").strip()
            if not family_name:
                continue
            result.setdefault(family_name, []).append(entry)
        return result

    async def _build_runtime_font_entries(
        self,
        workspace_id: int,
        font_configs: list[WorkspaceFontConfig],
    ) -> list[dict[str, str]]:
        """把字体配置转换为运行时下发条目，并优先使用资产表中的当前逻辑名。"""

        asset_map = await self._get_asset_map_by_ids(workspace_id, [item.asset_id for item in font_configs])
        runtime_entries: list[dict[str, str]] = []
        for item in font_configs:
            asset = asset_map.get(item.asset_id)
            runtime_asset_name = str(asset.name if asset is not None and asset.name else "").strip()
            recorded_asset_name = str(item.asset_name or "").strip()
            if not runtime_asset_name:
                raise AppException(
                    status_code=409,
                    code="FONT_ASSET_NAME_MISSING",
                    detail=f'字体配置 "{recorded_asset_name or item.id}" 缺少对应资产逻辑名，无法生成运行时字体包。',
                )
            if recorded_asset_name != runtime_asset_name:
                raise AppException(
                    status_code=409,
                    code="FONT_ASSET_NAME_MISMATCH",
                    detail=(
                        f'字体配置记录的 asset_name="{recorded_asset_name}" 与资产当前 name="{runtime_asset_name}" 不一致，'
                        "请先修正字体配置数据后再构建。"
                    ),
                )
            runtime_entries.append(
                {
                    "asset_name": runtime_asset_name,
                    "font_family": item.font_family,
                    "font_format": item.font_format,
                    "font_weight": item.font_weight,
                    "font_style": item.font_style,
                    "font_display": item.font_display,
                }
            )
        return runtime_entries

    async def enrich_asset_payloads(
        self,
        workspace_id: int,
        assets: list[WorkspaceAsset],
        payloads: list[dict],
    ) -> list[dict]:
        """为资产响应补充字体注册信息及受限操作提示。"""

        asset_ids = [asset.id for asset in assets]
        font_config_map = await self._get_font_config_map_by_asset_ids(workspace_id, asset_ids)
        enriched: list[dict] = []
        for asset, payload in zip(assets, payloads):
            font_config = font_config_map.get(asset.id)
            delete_block_reason: str | None = None
            if await self.workspace_theme_service.is_asset_referenced(workspace_id, asset.id):
                delete_block_reason = "已被主题引用，不可删除。"

            if asset.asset_type == AssetType.FONT.value:
                if font_config:
                    if await self._is_font_config_referenced(workspace_id, font_config):
                        delete_block_reason = "该字体已被项目主题引用，请先解除主题引用并删除字体配置。"
                    else:
                        delete_block_reason = "该字体已注册为可用字体，请先删除字体配置。"

            payload["font_config"] = self._to_asset_font_summary(font_config)
            payload["rename_block_reason"] = None
            payload["delete_block_reason"] = delete_block_reason
            enriched.append(payload)
        return enriched

    async def sync_asset_reference_name(self, asset: WorkspaceAsset) -> None:
        """当字体资产逻辑名变更时，同步更新字体注册表中的引用名。"""

        if asset.asset_type != AssetType.FONT.value:
            return

        font_config = await self._get_font_config_by_asset_id(asset.workspace_id, asset.id)
        if font_config is None or font_config.asset_name == asset.name:
            return

        await self._ensure_asset_name_not_registered(
            asset.workspace_id,
            asset.name,
            exclude_font_config_id=font_config.id,
        )
        font_config.asset_name = asset.name

    async def ensure_asset_can_delete(self, asset: WorkspaceAsset) -> None:
        """校验字体资产是否允许删除。"""

        if asset.asset_type != AssetType.FONT.value:
            return

        font_config = await self._get_font_config_by_asset_id(asset.workspace_id, asset.id)
        if font_config:
            if await self._is_font_config_referenced(asset.workspace_id, font_config):
                raise AppException(
                    status_code=409,
                    code="FONT_ASSET_DELETE_FORBIDDEN",
                    detail="该字体已被项目主题引用，请先解除主题引用并删除字体配置。",
                )
            raise AppException(
                status_code=409,
                code="FONT_ASSET_DELETE_FORBIDDEN",
                detail="该字体已注册为可用字体，请先删除字体配置。",
            )

    async def _get_font_asset_or_raise(self, workspace_id: int, asset_id: int) -> WorkspaceAsset:
        """获取并校验字体资产。"""

        asset = await self.session.scalar(
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.id == asset_id)
        )
        if asset is None:
            raise AppException(status_code=404, code="ASSET_NOT_FOUND", detail="未找到目标静态资源。")
        if asset.asset_type != AssetType.FONT.value:
            raise AppException(status_code=400, code="FONT_ASSET_REQUIRED", detail="仅允许将字体资源注册为字体配置。")
        return asset

    async def _get_font_config_or_raise(self, workspace_id: int, font_id: int) -> WorkspaceFontConfig:
        """按工作空间和主键获取字体配置。"""

        font_config = await self.session.scalar(
            select(WorkspaceFontConfig)
            .where(WorkspaceFontConfig.workspace_id == workspace_id)
            .where(WorkspaceFontConfig.id == font_id)
        )
        if font_config is None:
            raise AppException(status_code=404, code="FONT_CONFIG_NOT_FOUND", detail="未找到目标字体配置。")
        return font_config

    async def get_font_config_by_asset_id(self, workspace_id: int, asset_id: int) -> WorkspaceFontConfig | None:
        """按资产 ID 查询字体配置，供资产管理服务判断注册状态。"""

        return await self._get_font_config_by_asset_id(workspace_id, asset_id)

    async def _get_font_config_by_asset_id(self, workspace_id: int, asset_id: int) -> WorkspaceFontConfig | None:
        """按资产查询字体配置。"""

        return await self.session.scalar(
            select(WorkspaceFontConfig)
            .where(WorkspaceFontConfig.workspace_id == workspace_id)
            .where(WorkspaceFontConfig.asset_id == asset_id)
        )

    async def _get_family_or_raise(self, workspace_id: int, family_id: int) -> WorkspaceFontFamily:
        """按工作空间和主键获取字体族。"""

        family = await self.session.scalar(
            select(WorkspaceFontFamily)
            .where(WorkspaceFontFamily.workspace_id == workspace_id)
            .where(WorkspaceFontFamily.id == family_id)
        )
        if family is None:
            raise AppException(status_code=404, code="FONT_FAMILY_NOT_FOUND", detail="未找到目标字体族。")
        return family

    async def _get_or_create_family(self, workspace_id: int, name: str) -> WorkspaceFontFamily:
        """按名称（trim + 忽略大小写）获取字体族，不存在时创建。"""

        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise AppException(status_code=400, code="FONT_FAMILY_NAME_INVALID", detail="字体族名称不能为空。")
        existing = await self._find_family_by_name(workspace_id, normalized_name)
        if existing is not None:
            return existing
        family = WorkspaceFontFamily(workspace_id=workspace_id, name=normalized_name)
        self.session.add(family)
        await self.session.flush()
        return family

    async def _find_family_by_name(self, workspace_id: int, name: str) -> WorkspaceFontFamily | None:
        """按名称（trim + 忽略大小写）查找字体族。"""

        return await self.session.scalar(
            select(WorkspaceFontFamily)
            .where(WorkspaceFontFamily.workspace_id == workspace_id)
            .where(func.lower(func.trim(WorkspaceFontFamily.name)) == name.strip().lower())
        )

    async def _ensure_family_name_available(
        self,
        workspace_id: int,
        name: str,
        *,
        exclude_family_id: int | None = None,
    ) -> None:
        """确保字体族名称在工作空间内唯一。"""

        existing = await self._find_family_by_name(workspace_id, name)
        if existing is not None and existing.id != exclude_family_id:
            raise AppException(
                status_code=409,
                code="FONT_FAMILY_DUPLICATE_NAME",
                detail=f'字体族名称 "{name}" 已存在，请保持唯一。',
            )

    async def _cleanup_family_if_orphan(self, workspace_id: int, family: WorkspaceFontFamily) -> None:
        """字体族下已无 face 且未被可见主题绑定时级联删除，并释放软删除主题的残留外键。"""

        remaining = int(
            await self.session.scalar(
                select(func.count(WorkspaceFontConfig.id)).where(WorkspaceFontConfig.family_id == family.id)
            )
            or 0
        )
        if remaining:
            return
        if await self.workspace_theme_service.is_font_referenced(workspace_id, family.id):
            return
        await self.workspace_theme_service.purge_soft_deleted_theme_font_references(workspace_id, family.id)
        await self.session.delete(family)
        await self.session.flush()

    async def _to_family_responses(
        self,
        workspace_id: int,
        families: list[WorkspaceFontFamily],
    ) -> list[WorkspaceFontFamilyResponse]:
        """把字体族实体批量转换为内嵌 face 的响应。"""

        family_ids = [family.id for family in families]
        faces_by_family: dict[int, list[WorkspaceFontConfig]] = {}
        if family_ids:
            face_stmt = (
                select(WorkspaceFontConfig)
                .where(WorkspaceFontConfig.family_id.in_(family_ids))
                .order_by(WorkspaceFontConfig.id.asc())
            )
            for face in (await self.session.execute(face_stmt)).scalars().all():
                faces_by_family.setdefault(face.family_id, []).append(face)

        all_faces = [face for faces in faces_by_family.values() for face in faces]
        asset_map = await self._get_asset_map_by_ids(workspace_id, [face.asset_id for face in all_faces])
        responses: list[WorkspaceFontFamilyResponse] = []
        for family in families:
            face_responses: list[WorkspaceFontConfigResponse] = []
            for face in faces_by_family.get(family.id, []):
                face_response = self._to_response(face)
                asset = asset_map.get(face.asset_id)
                face_response.asset_url = self._build_asset_url(workspace_id, asset.file_hash) if asset else None
                face_responses.append(face_response)
            responses.append(
                WorkspaceFontFamilyResponse(
                    id=family.id,
                    workspace_id=family.workspace_id,
                    name=family.name,
                    faces=face_responses,
                    created_at=family.created_at,
                    updated_at=family.updated_at,
                )
            )
        return responses

    async def _ensure_asset_not_registered(self, workspace_id: int, asset_id: int) -> None:
        """确保同一资产不会被重复注册。"""

        if await self._get_font_config_by_asset_id(workspace_id, asset_id):
            raise AppException(
                status_code=409,
                code="FONT_CONFIG_ALREADY_EXISTS",
                detail="该字体资源已经注册为可用字体。",
            )

    async def _ensure_asset_name_not_registered(
        self,
        workspace_id: int,
        asset_name: str,
        *,
        exclude_font_config_id: int | None = None,
    ) -> None:
        """确保同名字体资源不会被重复注册。"""

        stmt = (
            select(WorkspaceFontConfig)
            .where(WorkspaceFontConfig.workspace_id == workspace_id)
            .where(WorkspaceFontConfig.asset_name == asset_name)
        )
        if exclude_font_config_id is not None:
            stmt = stmt.where(WorkspaceFontConfig.id != exclude_font_config_id)

        existing = await self.session.scalar(stmt)
        if existing:
            raise AppException(
                status_code=409,
                code="FONT_CONFIG_DUPLICATE_ASSET_NAME",
                detail=f'字体资源名 "{asset_name}" 已存在字体配置，请保持唯一。',
            )

    async def _ensure_font_face_signature_available(
        self,
        family: WorkspaceFontFamily,
        *,
        font_weight: str,
        font_style: str,
        exclude_font_config_id: int | None = None,
    ) -> None:
        """确保同一字体族内不会注册重复的 (font-weight, font-style) 字体面。"""

        if family.id is None:
            return

        normalized_weight = str(font_weight or "").strip()
        normalized_style = str(font_style or "").strip()
        stmt = (
            select(WorkspaceFontConfig)
            .where(WorkspaceFontConfig.family_id == family.id)
            .where(func.lower(func.trim(WorkspaceFontConfig.font_weight)) == normalized_weight.lower())
            .where(func.lower(func.trim(WorkspaceFontConfig.font_style)) == normalized_style.lower())
        )
        if exclude_font_config_id is not None:
            stmt = stmt.where(WorkspaceFontConfig.id != exclude_font_config_id)

        existing = await self.session.scalar(stmt)
        if existing:
            raise AppException(
                status_code=409,
                code="FONT_CONFIG_DUPLICATE_FACE",
                detail=(
                    f'字体 "{family.name}" 已存在相同 font-weight="{normalized_weight}" '
                    f'和 font-style="{normalized_style}" 的注册，请改用不同字重/样式或删除旧注册。'
                ),
            )

    async def _list_font_configs(self, workspace_id: int, only_active: bool = False) -> list[WorkspaceFontConfig]:
        """列出工作空间字体配置。"""

        stmt = (
            select(WorkspaceFontConfig)
            .where(WorkspaceFontConfig.workspace_id == workspace_id)
            .order_by(WorkspaceFontConfig.updated_at.desc(), WorkspaceFontConfig.id.desc())
        )
        if only_active:
            stmt = stmt.where(WorkspaceFontConfig.status == RecordStatus.ACTIVE.value)
        return list((await self.session.execute(stmt)).scalars().all())

    async def _list_font_configs_page(
        self,
        workspace_id: int,
        query: ListQuery,
    ) -> tuple[list[WorkspaceFontConfig], int]:
        """按分页、状态和关键词列出字体配置。"""

        stmt = select(WorkspaceFontConfig).where(WorkspaceFontConfig.workspace_id == workspace_id)
        count_stmt = select(func.count(WorkspaceFontConfig.id)).where(WorkspaceFontConfig.workspace_id == workspace_id)

        if query.status is not None:
            stmt = stmt.where(WorkspaceFontConfig.status == query.status.value)
            count_stmt = count_stmt.where(WorkspaceFontConfig.status == query.status.value)

        normalized_keyword = str(query.keyword or "").strip()
        # font_family 已退化为派生属性，关键词筛选与 font_family 排序都需要连接字体族表。
        sort_by_family_name = query.sort_by == "font_family"
        family_join_clause = WorkspaceFontConfig.family_id == WorkspaceFontFamily.id
        if normalized_keyword or sort_by_family_name:
            stmt = stmt.join(WorkspaceFontFamily, family_join_clause)
        if normalized_keyword:
            like_keyword = f"%{normalized_keyword}%"
            condition = or_(
                WorkspaceFontConfig.asset_name.ilike(like_keyword),
                WorkspaceFontFamily.name.ilike(like_keyword),
                WorkspaceFontConfig.font_format.ilike(like_keyword),
                WorkspaceFontConfig.font_weight.ilike(like_keyword),
                WorkspaceFontConfig.font_style.ilike(like_keyword),
                WorkspaceFontConfig.font_display.ilike(like_keyword),
            )
            stmt = stmt.where(condition)
            count_stmt = (
                count_stmt
                .select_from(WorkspaceFontConfig)
                .join(WorkspaceFontFamily, family_join_clause)
                .where(condition)
            )

        if sort_by_family_name:
            sort_column = WorkspaceFontFamily.name
        else:
            sort_column = getattr(WorkspaceFontConfig, query.sort_by, None)
            if sort_column is None or not hasattr(sort_column, "asc"):
                sort_column = WorkspaceFontConfig.updated_at
        sort_expression = sort_column.asc() if query.sort_order == "asc" else sort_column.desc()
        stmt = (
            stmt
            .order_by(sort_expression, WorkspaceFontConfig.id.desc())
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        total = int(await self.session.scalar(count_stmt) or 0)
        return list((await self.session.execute(stmt)).scalars().all()), total

    async def _get_font_config_map_by_asset_ids(
        self,
        workspace_id: int,
        asset_ids: list[int],
    ) -> dict[int, WorkspaceFontConfig]:
        """按资产 ID 批量读取字体配置。"""

        if not asset_ids:
            return {}

        stmt = (
            select(WorkspaceFontConfig)
            .where(WorkspaceFontConfig.workspace_id == workspace_id)
            .where(WorkspaceFontConfig.asset_id.in_(asset_ids))
        )
        items = (await self.session.execute(stmt)).scalars().all()
        return {item.asset_id: item for item in items}

    async def _get_asset_map_by_ids(self, workspace_id: int, asset_ids: list[int]) -> dict[int, WorkspaceAsset]:
        """按资产 ID 批量读取工作空间资产。"""

        if not asset_ids:
            return {}

        stmt = (
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.id.in_(asset_ids))
        )
        items = (await self.session.execute(stmt)).scalars().all()
        return {item.id: item for item in items}

    async def _is_font_config_referenced(self, workspace_id: int, font_config: WorkspaceFontConfig) -> bool:
        """判断该 face 是否为被主题引用字体族的最后一个 face（此时不允许删除）。"""

        if not await self.workspace_theme_service.is_font_referenced(workspace_id, font_config.family_id):
            return False
        sibling_count = int(
            await self.session.scalar(
                select(func.count(WorkspaceFontConfig.id))
                .where(WorkspaceFontConfig.family_id == font_config.family_id)
                .where(WorkspaceFontConfig.id != font_config.id)
            )
            or 0
        )
        return sibling_count == 0

    @staticmethod
    def _build_font_config_in_use_error(font_config: WorkspaceFontConfig) -> AppException:
        """构造字体仍被主题引用的友好业务错误。"""

        return AppException(
            status_code=409,
            code="FONT_CONFIG_IN_USE",
            detail=f'字体配置 "{font_config.asset_name}" 所属字体族仍被主题引用且无其他字体文件，请先切换相关主题字体后再删除。',
        )

    def _to_response(self, font_config: WorkspaceFontConfig | None) -> WorkspaceFontConfigResponse | None:
        """把 ORM 字体配置转换为接口响应。"""

        if font_config is None:
            return None
        return WorkspaceFontConfigResponse.model_validate(font_config)

    def _to_asset_font_summary(self, font_config: WorkspaceFontConfig | None) -> dict | None:
        """把 ORM 字体配置转换为资产接口可嵌入的摘要字典。"""

        if font_config is None:
            return None
        return AssetFontConfigSummary.model_validate(font_config).model_dump()

    @staticmethod
    def _infer_font_format(asset_name: str) -> str:
        """根据资产文件名推断字体格式。"""

        suffixes = [suffix.lstrip(".").lower() for suffix in Path(asset_name).suffixes]
        for candidate in reversed(suffixes):
            if candidate in {"woff2", "woff", "ttf", "otf"}:
                return candidate
        return "woff2"

    @staticmethod
    def _normalize_font_format(font_format: str) -> str:
        """规范化字体格式字段。"""

        normalized = str(font_format or "").strip().lower()
        if normalized not in {"woff2", "woff", "ttf", "otf"}:
            raise AppException(status_code=400, code="FONT_FORMAT_INVALID", detail="字体格式仅支持 woff2、woff、ttf、otf。")
        return normalized

    @staticmethod
    def _normalize_font_weight(font_weight: str) -> str:
        """规范化 font-weight，允许单值数字或可变字体范围 "min max"。"""

        normalized = str(font_weight or "").strip()
        if FONT_WEIGHT_VALUE_PATTERN.match(normalized):
            return normalized
        range_match = FONT_WEIGHT_RANGE_PATTERN.match(normalized)
        if range_match and int(range_match.group(1)) <= int(range_match.group(2)):
            return normalized
        raise AppException(
            status_code=400,
            code="FONT_WEIGHT_INVALID",
            detail='font-weight 仅支持数字（如 "400"）或可变字体范围（如 "100 900"，且最小值不大于最大值）。',
        )

    @staticmethod
    def _normalize_font_style(font_style: str) -> str:
        """规范化 font-style，仅允许 normal/italic/oblique。"""

        normalized = str(font_style or "").strip().lower()
        if normalized not in FONT_STYLE_ALLOWED_VALUES:
            raise AppException(status_code=400, code="FONT_STYLE_INVALID", detail="font-style 仅支持 normal、italic、oblique。")
        return normalized

    @staticmethod
    def _normalize_font_display(font_display: str) -> str:
        """规范化 font-display，仅允许标准枚举值。"""

        normalized = str(font_display or "").strip().lower()
        if normalized not in FONT_DISPLAY_ALLOWED_VALUES:
            raise AppException(
                status_code=400,
                code="FONT_DISPLAY_INVALID",
                detail="font-display 仅支持 auto、block、swap、fallback、optional。",
            )
        return normalized

    @staticmethod
    def _build_asset_url(workspace_id: int, file_hash: str) -> str:
        """构建字体资产公开访问地址。"""

        settings = get_settings()
        return f"{settings.backend_public_base_url.rstrip('/')}/public/assets/{workspace_id}/{file_hash}"

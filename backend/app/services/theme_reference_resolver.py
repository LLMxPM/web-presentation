"""文件功能：负责工作空间主题引用的资源与字体族校验、真值表解析与清空语义处理。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.platform_fonts import (
    MONO_FONT_PRESETS,
    PLATFORM_MONO_FONT,
    PLATFORM_SANS_FONT,
    SANS_FONT_PRESETS,
)
from app.models.asset import WorkspaceAsset
from app.models.enums import AssetType, RecordStatus
from app.models.font import WorkspaceFontConfig, WorkspaceFontFamily

if TYPE_CHECKING:
    from app.models.workspace_theme import WorkspaceTheme
    from app.schemas.theme import (
        WorkspaceThemeCreateRequest,
        WorkspaceThemeUpdateRequest,
    )

DEFAULT_THEME_PROJECT_ICON_NAME: str | None = None
DEFAULT_THEME_HEADING_FONT: str = PLATFORM_SANS_FONT
DEFAULT_THEME_BODY_FONT: str = PLATFORM_SANS_FONT
DEFAULT_THEME_CODE_FONT: str = PLATFORM_MONO_FONT


async def validate_and_get_theme_asset(
    session: AsyncSession,
    workspace_id: int,
    asset_id: int | None,
    allowed_types: set[str],
    field_description: str,
) -> WorkspaceAsset | None:
    """校验并获取主题引用的静态资产。

    职责：
    1. 校验资产必须属于当前工作空间且存在。
    2. 校验资产不能处于归档状态。
    3. 校验资产不能是替换产生的历史副本。
    4. 校验资产类型必须符合允许的类型集合。

    输入：session 数据库会话，workspace_id 工作空间 ID，asset_id 资产 ID，allowed_types 允许的类型，field_description 字段中文描述。
    输出：合格的 WorkspaceAsset 对象，若 asset_id 为 None 则返回 None。
    约束：不合法时抛出 AppException(400)。
    """
    if asset_id is None:
        return None

    asset = await session.scalar(
        select(WorkspaceAsset)
        .where(WorkspaceAsset.workspace_id == workspace_id)
        .where(WorkspaceAsset.id == asset_id)
    )
    if asset is None:
        raise AppException(
            status_code=400,
            code="WORKSPACE_THEME_ASSET_NOT_FOUND",
            detail=f"主题引用的{field_description}资产不存在。",
        )
    if asset.status != RecordStatus.ACTIVE.value or asset.archived_at is not None:
        raise AppException(
            status_code=400,
            code="WORKSPACE_THEME_ASSET_INVALID",
            detail=f"主题引用的{field_description}资产已被归档。",
        )
    if asset.history_kind is not None:
        raise AppException(
            status_code=400,
            code="WORKSPACE_THEME_ASSET_INVALID",
            detail=f"不能引用{field_description}资产的历史副本。",
        )
    if asset.asset_type not in allowed_types:
        raise AppException(
            status_code=400,
            code="WORKSPACE_THEME_ASSET_INVALID",
            detail=f"主题{field_description}资源类型不受支持。",
        )
    return asset


async def validate_and_get_font_family(
    session: AsyncSession,
    workspace_id: int,
    family_id: int | None,
    slot_name: str,
) -> WorkspaceFontFamily | None:
    """校验并获取主题引用的字体族。

    职责：
    1. 校验字体族存在且属于当前工作空间。
    2. 校验字体族必须至少拥有一个处于 active 状态且关联有效资产的 face。

    输入：session 数据库会话，workspace_id 工作空间 ID，family_id 字体族 ID，slot_name 槽位名称。
    输出：合格的 WorkspaceFontFamily 对象，若 family_id 为 None 则返回 None。
    约束：不合法时抛出 AppException(400)。
    """
    if family_id is None:
        return None

    family = await session.scalar(
        select(WorkspaceFontFamily)
        .where(WorkspaceFontFamily.workspace_id == workspace_id)
        .where(WorkspaceFontFamily.id == family_id)
    )
    if family is None:
        raise AppException(
            status_code=400,
            code="WORKSPACE_THEME_FONT_NOT_FOUND",
            detail=f"主题{slot_name}引用的字体族不存在。",
        )

    # 校验字体族内必须存在有效启用的 face
    active_faces = (
        await session.execute(
            select(WorkspaceFontConfig)
            .join(WorkspaceAsset, WorkspaceFontConfig.asset_id == WorkspaceAsset.id)
            .where(WorkspaceFontConfig.workspace_id == workspace_id)
            .where(WorkspaceFontConfig.family_id == family_id)
            .where(WorkspaceFontConfig.status == RecordStatus.ACTIVE.value)
            .where(WorkspaceAsset.status == RecordStatus.ACTIVE.value)
            .where(WorkspaceAsset.archived_at.is_(None))
            .where(WorkspaceAsset.history_kind.is_(None))
        )
    ).scalars().all()

    if not active_faces:
        raise AppException(
            status_code=400,
            code="WORKSPACE_THEME_FONT_INVALID",
            detail=f"主题{slot_name}引用的字体族没有可用的字体配置。",
        )

    return family


async def safe_load_theme_relations(
    session: AsyncSession,
    workspace_id: int,
    logo_asset_id: int | None,
    invert_logo_asset_id: int | None,
    project_icon_asset_id: int | None,
    heading_font_family_id: int | None,
    body_font_family_id: int | None,
    code_font_family_id: int | None,
) -> tuple[
    WorkspaceAsset | None,
    WorkspaceAsset | None,
    WorkspaceAsset | None,
    WorkspaceFontFamily | None,
    WorkspaceFontFamily | None,
    WorkspaceFontFamily | None,
]:
    """安全读取主题关联关系，用于只读查询，避免历史脏引用导致详情接口报错崩溃。

    输入：session、workspace_id 及主题中记录的各个外键 ID。
    输出：对应的实体对象（失效或不存在时优雅回退为 None）。
    """
    async def _safe_get_asset(aid: int | None) -> WorkspaceAsset | None:
        if aid is None:
            return None
        return await session.scalar(
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.id == aid)
        )

    async def _safe_get_family(fid: int | None) -> WorkspaceFontFamily | None:
        if fid is None:
            return None
        return await session.scalar(
            select(WorkspaceFontFamily)
            .where(WorkspaceFontFamily.workspace_id == workspace_id)
            .where(WorkspaceFontFamily.id == fid)
        )

    logo = await _safe_get_asset(logo_asset_id)
    invert = await _safe_get_asset(invert_logo_asset_id)
    icon = await _safe_get_asset(project_icon_asset_id)
    heading_family = await _safe_get_family(heading_font_family_id)
    body_family = await _safe_get_family(body_font_family_id)
    code_family = await _safe_get_family(code_font_family_id)
    return logo, invert, icon, heading_family, body_family, code_family


def _resolve_image_slot(
    payload_fields: set[str],
    field_name: str,
    asset: WorkspaceAsset | None,
    current_asset_id: int | None,
    current_path_or_name: str | None,
    default_fallback: str | None = None,
) -> tuple[int | None, str | None]:
    """解析单个图片槽位的 asset_id 与持久化路径/名称。

    规则：
    - 显式提交字段且值为 None 时：清空槽位，返回 (None, None)。
    - 显式提交字段且有合法资产时：更新槽位，返回 (asset.id, asset.name)。
    - 未提交该字段时：保留原有值 (current_asset_id, current_path_or_name)，若均无则返回 (None, default_fallback)。
    """
    if field_name in payload_fields:
        if asset is None:
            return None, None
        return asset.id, asset.name
    if current_asset_id is not None or current_path_or_name is not None:
        return current_asset_id, current_path_or_name
    return None, default_fallback


def _resolve_font_slot_truth_table(
    slot_name: str,
    payload_fields: set[str],
    family_field_name: str,
    preset_field_name: str,
    raw_family_id: int | None,
    raw_preset: str | None,
    validated_family: WorkspaceFontFamily | None,
    allowed_presets: frozenset[str],
    default_preset: str,
    current_family_id: int | None,
    current_label: str | None,
) -> tuple[int | None, str]:
    """严格执行字体槽位的真值表解析。

    返回：(family_id, label)。
    """
    family_in_fields = family_field_name in payload_fields
    preset_in_fields = preset_field_name in payload_fields
    normalized_preset = str(raw_preset or "").strip() or None

    # 1. 双省略：保持原有状态
    if not family_in_fields and not preset_in_fields:
        if current_label is not None:
            return current_family_id, current_label
        return None, default_preset

    # 2. 双非空：互斥错误
    has_non_null_family = family_in_fields and raw_family_id is not None
    has_non_null_preset = preset_in_fields and normalized_preset is not None
    if has_non_null_family and has_non_null_preset:
        raise AppException(
            status_code=422,
            code="MUTUALLY_EXCLUSIVE_FONT_SOURCE",
            detail=f"{slot_name}字体不能同时选择字体族和内置预设。",
        )

    # 3. 显式选择非空字体族（此时 preset 未传或为 None）
    if has_non_null_family:
        assert validated_family is not None
        return validated_family.id, validated_family.name

    # 4. 显式选择非空内置预设（此时 family 未传或为 None）
    if has_non_null_preset:
        assert normalized_preset is not None
        if normalized_preset not in allowed_presets:
            raise AppException(
                status_code=422,
                code="UNSUPPORTED_FONT_PRESET",
                detail=f"{slot_name}字体预设不受支持。",
            )
        return None, normalized_preset

    # 5. 显式清空（单独传 null 或同时传 null，未提供新非空来源）：恢复平台默认
    return None, default_preset


async def resolve_theme_references(
    session: AsyncSession,
    workspace_id: int,
    payload: WorkspaceThemeCreateRequest | WorkspaceThemeUpdateRequest,
    *,
    current_theme: WorkspaceTheme | None = None,
) -> dict[str, object]:
    """解析主题请求中的图片与字体引用，处理字段存在性、真值表与清空语义。

    输入：
    - session: 数据库会话
    - workspace_id: 目标工作空间 ID
    - payload: 主题创建或更新请求 DTO
    - current_theme: 更新时的当前主题实体（创建时为 None）

    输出：包含已解析字段的字典，供仓储层直接持久化。
    """
    payload_fields = getattr(payload, "model_fields_set", set())

    # 1. 解析并校验图片资产
    logo_asset: WorkspaceAsset | None = None
    invert_logo_asset: WorkspaceAsset | None = None
    project_icon_asset: WorkspaceAsset | None = None

    if "logo_asset_id" in payload_fields and payload.logo_asset_id is not None:
        logo_asset = await validate_and_get_theme_asset(
            session,
            workspace_id,
            payload.logo_asset_id,
            allowed_types={AssetType.ICON.value, AssetType.IMAGE.value},
            field_description="logo",
        )

    if "invert_logo_asset_id" in payload_fields and payload.invert_logo_asset_id is not None:
        invert_logo_asset = await validate_and_get_theme_asset(
            session,
            workspace_id,
            payload.invert_logo_asset_id,
            allowed_types={AssetType.ICON.value, AssetType.IMAGE.value},
            field_description="反色 logo",
        )

    if "project_icon_asset_id" in payload_fields and payload.project_icon_asset_id is not None:
        project_icon_asset = await validate_and_get_theme_asset(
            session,
            workspace_id,
            payload.project_icon_asset_id,
            allowed_types={AssetType.ICON.value},
            field_description="项目图标",
        )

    logo_id, logo_path = _resolve_image_slot(
        payload_fields,
        "logo_asset_id",
        logo_asset,
        current_theme.logo_asset_id if current_theme else None,
        current_theme.logo_path if current_theme else None,
    )
    invert_logo_id, invert_logo_path = _resolve_image_slot(
        payload_fields,
        "invert_logo_asset_id",
        invert_logo_asset,
        current_theme.invert_logo_asset_id if current_theme else None,
        current_theme.invert_logo_path if current_theme else None,
    )
    icon_id, icon_name = _resolve_image_slot(
        payload_fields,
        "project_icon_asset_id",
        project_icon_asset,
        current_theme.project_icon_asset_id if current_theme else None,
        current_theme.project_icon_name if current_theme else None,
        default_fallback=DEFAULT_THEME_PROJECT_ICON_NAME,
    )

    # 2. 校验字体族
    heading_font_family: WorkspaceFontFamily | None = None
    body_font_family: WorkspaceFontFamily | None = None
    code_font_family: WorkspaceFontFamily | None = None

    if "heading_font_family_id" in payload_fields and payload.heading_font_family_id is not None:
        heading_font_family = await validate_and_get_font_family(
            session, workspace_id, payload.heading_font_family_id, "标题"
        )
    if "body_font_family_id" in payload_fields and payload.body_font_family_id is not None:
        body_font_family = await validate_and_get_font_family(
            session, workspace_id, payload.body_font_family_id, "正文"
        )
    if "code_font_family_id" in payload_fields and payload.code_font_family_id is not None:
        code_font_family = await validate_and_get_font_family(
            session, workspace_id, payload.code_font_family_id, "代码"
        )

    # 3. 执行三槽字体真值表
    heading_family_id, heading_label = _resolve_font_slot_truth_table(
        slot_name="标题",
        payload_fields=payload_fields,
        family_field_name="heading_font_family_id",
        preset_field_name="heading_font_preset",
        raw_family_id=payload.heading_font_family_id,
        raw_preset=payload.heading_font_preset,
        validated_family=heading_font_family,
        allowed_presets=SANS_FONT_PRESETS,
        default_preset=DEFAULT_THEME_HEADING_FONT,
        current_family_id=current_theme.heading_font_family_id if current_theme else None,
        current_label=current_theme.heading_font_label if current_theme else None,
    )

    body_family_id, body_label = _resolve_font_slot_truth_table(
        slot_name="正文",
        payload_fields=payload_fields,
        family_field_name="body_font_family_id",
        preset_field_name="body_font_preset",
        raw_family_id=payload.body_font_family_id,
        raw_preset=payload.body_font_preset,
        validated_family=body_font_family,
        allowed_presets=SANS_FONT_PRESETS,
        default_preset=DEFAULT_THEME_BODY_FONT,
        current_family_id=current_theme.body_font_family_id if current_theme else None,
        current_label=current_theme.body_font_label if current_theme else None,
    )

    code_family_id, code_label = _resolve_font_slot_truth_table(
        slot_name="代码",
        payload_fields=payload_fields,
        family_field_name="code_font_family_id",
        preset_field_name="code_font_preset",
        raw_family_id=payload.code_font_family_id,
        raw_preset=payload.code_font_preset,
        validated_family=code_font_family,
        allowed_presets=MONO_FONT_PRESETS,
        default_preset=DEFAULT_THEME_CODE_FONT,
        current_family_id=current_theme.code_font_family_id if current_theme else None,
        current_label=current_theme.code_font_label if current_theme else None,
    )

    return {
        "logo_asset_id": logo_id,
        "invert_logo_asset_id": invert_logo_id,
        "project_icon_asset_id": icon_id,
        "logo_path": logo_path,
        "invert_logo_path": invert_logo_path,
        "project_icon_name": icon_name,
        "heading_font_family_id": heading_family_id,
        "body_font_family_id": body_family_id,
        "code_font_family_id": code_family_id,
        "heading_font_label": heading_label,
        "body_font_label": body_label,
        "code_font_label": code_label,
    }

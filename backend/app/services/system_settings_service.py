"""文件功能：系统设置管理服务，负责持久化配置读写、分类组织、掩码脱敏、前置校验与 S3 连通性实测。"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import (
    apply_system_settings_override,
    get_settings,
    get_settings_safe_mode_warnings,
)
from app.core.system_settings_spec import (
    SYSTEM_SETTING_SPECS,
    is_env_overridden,
    safe_mode_convert_value,
)
from app.core.time_utils import utc_now
from app.core.exceptions import AppException
from app.models.system_setting import SystemSetting
from app.schemas.system_setting import (
    S3TestConnectionRequest,
    S3TestConnectionResponse,
    SystemSettingCategoryGroup,
    SystemSettingItem,
    SystemSettingsListResponse,
)

logger = logging.getLogger(__name__)

CATEGORY_NAMES: dict[str, str] = {
    "storage": "存储管理",
    "general": "常规设置",
    "security": "安全策略",
    "ai": "AI 运营",
    "diagnostic": "系统诊断",
}

CATEGORY_ORDER: list[str] = ["storage", "general", "security", "ai", "diagnostic"]


class SystemSettingsService:
    """系统设置管理服务。"""

    def __init__(self, session: AsyncSession) -> None:
        """初始化服务。"""
        self.session = session

    async def list_settings(self) -> SystemSettingsListResponse:
        """获取全量系统设置列表，按分类组织并附带来源与脱敏信息。"""
        stmt = select(SystemSetting)
        result = await self.session.execute(stmt)
        db_rows = {row.key: row for row in result.scalars().all()}

        current_settings = get_settings()
        items: list[SystemSettingItem] = []

        for key, spec in SYSTEM_SETTING_SPECS.items():
            env_override = is_env_overridden(key)
            db_row = db_rows.get(key)

            if env_override:
                source = "env"
                raw_val = getattr(current_settings, key, spec.default_value)
                updated_at = None
                updated_by = None
            elif db_row is not None:
                source = "db"
                raw_val = db_row.value
                updated_at = db_row.updated_at
                updated_by = db_row.updated_by
            else:
                source = "default"
                raw_val = getattr(current_settings, key, spec.default_value)
                updated_at = None
                updated_by = None

            masked_val = spec.mask_value(raw_val)

            items.append(
                SystemSettingItem(
                    key=key,
                    category=spec.category,
                    description=spec.description,
                    value=masked_val,
                    is_secret=spec.is_secret,
                    is_env_overridden=env_override,
                    source=source,
                    updated_at=updated_at,
                    updated_by=updated_by,
                )
            )

        # 按分类组织
        categories: list[SystemSettingCategoryGroup] = []
        for cat in CATEGORY_ORDER:
            cat_items = [item for item in items if item.category == cat]
            categories.append(
                SystemSettingCategoryGroup(
                    category=cat,
                    category_name=CATEGORY_NAMES.get(cat, cat),
                    items=cat_items,
                )
            )

        return SystemSettingsListResponse(
            items=items,
            categories=categories,
            safe_mode_warnings=get_settings_safe_mode_warnings(),
        )

    async def update_settings(
        self,
        updates: dict[str, Any],
        user_id: int | None = None,
    ) -> SystemSettingsListResponse:
        """批量校验并更新系统设置，写穿数据库并在进程内原子热更新。"""
        if not updates:
            return await self.list_settings()

        current_settings = get_settings()

        # 1. 存在性与非法 key 拦截
        for key in updates:
            if key not in SYSTEM_SETTING_SPECS:
                raise AppException(
                    status_code=400,
                    code="UNKNOWN_SETTING_KEY",
                    detail=f"不支持的系统配置项：{key}。",
                )

        # 2. 环境变量锁定（ENV 否决权）不可篡改校验：允许与当前生效值一致的幂等提交，仅拦截真篡改
        keys_to_skip: set[str] = set()
        for key, val in updates.items():
            if is_env_overridden(key):
                current_active_val = getattr(current_settings, key, None)
                spec = SYSTEM_SETTING_SPECS[key]
                if spec.is_secret and (val is None or "******" in str(val)):
                    keys_to_skip.add(key)
                    continue
                converted_val, _ = safe_mode_convert_value(key, val)
                if converted_val == current_active_val:
                    keys_to_skip.add(key)
                    continue
                raise AppException(
                    status_code=400,
                    code="ENV_OVERRIDDEN_IMMUTABLE",
                    detail=f"配置项 {key} 已被环境变量强制覆盖锁定，无法通过 Web UI 修改。",
                )

        # 3. 守卫复核：存储驱动合法性与 S3 凭证完整性校验
        driver_candidate = str(updates.get("asset_storage_driver") or "").strip().lower()
        if driver_candidate == "local":
            if current_settings.backend_multi_instance and not current_settings.object_storage_shared_volume:
                raise AppException(
                    status_code=400,
                    code="INVALID_STORAGE_DRIVER",
                    detail="多 Backend 集群部署下对象存储必须为 S3，不支持切换为本地存储（local）。",
                )
        elif driver_candidate == "s3":
            effective_bucket = updates.get("s3_bucket") or current_settings.s3_bucket
            effective_ak = updates.get("s3_access_key") or current_settings.s3_access_key
            effective_sk = updates.get("s3_secret_key") or current_settings.s3_secret_key
            if not effective_bucket or not effective_ak or not effective_sk:
                raise AppException(
                    status_code=400,
                    code="S3_CONFIG_INCOMPLETE",
                    detail="切换为 S3 存储驱动必须提供完整的 Bucket 名称、Access Key 与 Secret Key。",
                )

        # 4. 前置 Dry-Run 校验（Pydantic / Spec validator 实测）
        validated_values: dict[str, Any] = {}
        for key, val in updates.items():
            if key in keys_to_skip:
                continue
            spec = SYSTEM_SETTING_SPECS[key]
            # 对 secret 字段如果传入包含掩码字符，则跳过修改以保持原密码
            if spec.is_secret and val is not None and "******" in str(val):
                continue

            converted, err = safe_mode_convert_value(key, val)
            if err:
                raise AppException(
                    status_code=400,
                    code="SETTING_VALIDATION_ERROR",
                    detail=f"配置项 {key} 值非法：{err}。",
                )
            validated_values[key] = converted

        # 5. 读取现有 DB 数据以支持事务合并
        stmt = select(SystemSetting)
        result = await self.session.execute(stmt)
        existing_rows = {row.key: row for row in result.scalars().all()}
        now = utc_now()

        for key, val in validated_values.items():
            spec = SYSTEM_SETTING_SPECS[key]
            if key in existing_rows:
                row = existing_rows[key]
                row.value = val
                row.updated_at = now
                row.updated_by = user_id
            else:
                new_row = SystemSetting(
                    key=key,
                    value=val,
                    category=spec.category,
                    description=spec.description,
                    is_secret=spec.is_secret,
                    updated_at=now,
                    updated_by=user_id,
                )
                self.session.add(new_row)

        await self.session.commit()

        # 6. 从数据库重新全量读取，触发热更新
        stmt_all = select(SystemSetting)
        res_all = await self.session.execute(stmt_all)
        db_all = {r.key: r.value for r in res_all.scalars().all()}
        apply_system_settings_override(db_all)

        return await self.list_settings()

    async def test_s3_connection(self, request: S3TestConnectionRequest) -> S3TestConnectionResponse:
        """实测 S3 兼容对象存储连通性与 Bucket 权限。"""
        try:
            import aioboto3
            from botocore.exceptions import ClientError
        except ImportError:
            return S3TestConnectionResponse(
                success=False,
                message="服务端未安装 aioboto3 依赖，无法测试 S3 存储连通性。",
            )

        current = get_settings()
        # 处理凭据回填：若用户未输入或使用掩码，尝试读取系统已有凭据
        ak = request.access_key
        if not ak or "******" in ak:
            ak = current.s3_access_key

        sk = request.secret_key
        if not sk or "******" in sk:
            sk = current.s3_secret_key

        endpoint = request.endpoint_url if request.endpoint_url is not None else current.s3_endpoint_url
        region = request.region if request.region is not None else current.s3_region

        if not ak or not sk:
            return S3TestConnectionResponse(
                success=False,
                message="测试连通性失败：必须提供有效的 S3 Access Key 与 Secret Key。",
            )

        try:
            session = aioboto3.Session()
            async with session.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=ak,
                aws_secret_access_key=sk,
                region_name=region,
            ) as client:
                # 发起真实探测请求测试 Bucket 连通性
                await client.head_bucket(Bucket=request.bucket)
            return S3TestConnectionResponse(
                success=True,
                message=f"S3 存储桶 [{request.bucket}] 连通性测试成功，权限正常。",
            )
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            error_msg = exc.response.get("Error", {}).get("Message", str(exc))
            return S3TestConnectionResponse(
                success=False,
                message=f"S3 连通性测试失败 [{error_code}]: {error_msg}",
            )
        except Exception as exc:  # noqa: BLE001
            return S3TestConnectionResponse(
                success=False,
                message=f"S3 连通性测试异常: {exc}",
            )


async def load_system_settings_on_startup(session: AsyncSession) -> None:
    """应用启动时从数据库加载系统设置并应用覆盖层，安全容错。"""
    try:
        stmt = select(SystemSetting)
        result = await session.execute(stmt)
        rows = result.scalars().all()
        if rows:
            db_map = {row.key: row.value for row in rows}
            apply_system_settings_override(db_map)
            logger.info("已从数据库加载并生效 %d 项系统设置。", len(db_map))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "应用启动加载系统设置失败（表可能未就绪），保持默认配置继续运行: %s",
            exc,
            extra={"event": "system_settings.startup_load_failed"},
        )

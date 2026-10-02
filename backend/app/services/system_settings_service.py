"""文件功能：系统设置管理服务，负责持久化配置读写、分类组织、掩码脱敏、前置校验与 S3 连通性实测。"""

import asyncio
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.asset import WorkspaceAsset
from app.models.enums import RecordStatus

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

        # 3. 前置 Dry-Run 校验与规范化（Pydantic / Spec validator 实测）
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

        # 4. 守卫复核：计算最终生效配置状态（合并 validated_values 与 current_settings）
        candidate_driver = validated_values.get("asset_storage_driver", current_settings.asset_storage_driver)
        if candidate_driver:
            candidate_driver = str(candidate_driver).strip().lower()

        if candidate_driver == "local":
            if current_settings.backend_multi_instance and not current_settings.object_storage_shared_volume:
                raise AppException(
                    status_code=400,
                    code="INVALID_STORAGE_DRIVER",
                    detail="多 Backend 集群部署下对象存储必须为 S3，不支持切换为本地存储（local）。",
                )
            if current_settings.asset_storage_driver == "s3":
                stmt_asset = select(func.count(WorkspaceAsset.id)).where(WorkspaceAsset.status == RecordStatus.ACTIVE.value)
                res = await self.session.execute(stmt_asset)
                scalar_val = res.scalar() if hasattr(res, "scalar") else None
                try:
                    asset_count = int(scalar_val or 0)
                except (TypeError, ValueError):
                    asset_count = 0
                if asset_count > 0:
                    raise AppException(
                        status_code=400,
                        code="STORAGE_MIGRATION_REQUIRED",
                        detail=f"当前系统已有 {asset_count} 项存量资源使用 S3 存储，直接切回本地存储将导致历史对象丢失访问，请先完成数据迁移。",
                    )
        elif candidate_driver == "s3":
            candidate_bucket = validated_values["s3_bucket"] if "s3_bucket" in validated_values else current_settings.s3_bucket
            candidate_ak = validated_values["s3_access_key"] if "s3_access_key" in validated_values else current_settings.s3_access_key
            candidate_sk = validated_values["s3_secret_key"] if "s3_secret_key" in validated_values else current_settings.s3_secret_key
            if not candidate_bucket or not candidate_ak or not candidate_sk:
                raise AppException(
                    status_code=400,
                    code="S3_CONFIG_INCOMPLETE",
                    detail="启用或保持 S3 存储驱动必须提供完整的 Bucket 名称、Access Key 与 Secret Key，不得清空必需凭据。",
                )
            if current_settings.asset_storage_driver == "local":
                stmt_asset = select(func.count(WorkspaceAsset.id)).where(WorkspaceAsset.status == RecordStatus.ACTIVE.value)
                res = await self.session.execute(stmt_asset)
                scalar_val = res.scalar() if hasattr(res, "scalar") else None
                try:
                    asset_count = int(scalar_val or 0)
                except (TypeError, ValueError):
                    asset_count = 0
                if asset_count > 0:
                    raise AppException(
                        status_code=400,
                        code="STORAGE_MIGRATION_REQUIRED",
                        detail=f"当前系统已有 {asset_count} 项存量资源使用本地存储，直接切换到 S3 存储将导致浏览器公开访问无法定位存量文件，请先完成数据迁移。",
                    )
            elif current_settings.asset_storage_driver == "s3" and current_settings.s3_bucket and candidate_bucket != current_settings.s3_bucket:
                stmt_asset = select(func.count(WorkspaceAsset.id)).where(WorkspaceAsset.status == RecordStatus.ACTIVE.value)
                res = await self.session.execute(stmt_asset)
                scalar_val = res.scalar() if hasattr(res, "scalar") else None
                try:
                    asset_count = int(scalar_val or 0)
                except (TypeError, ValueError):
                    asset_count = 0
                if asset_count > 0:
                    raise AppException(
                        status_code=400,
                        code="BUCKET_MIGRATION_REQUIRED",
                        detail=f"当前存储桶 [{current_settings.s3_bucket}] 中已有 {asset_count} 项存量资源，不支持直接更换为新存储桶 [{candidate_bucket}]，请先迁移数据。",
                    )

        # 5. 读取现有 DB 数据以支持事务合并，并同事务原子递增持久化版本号 _settings_version
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

        # 同事务原子递增持久化版本号
        if "_settings_version" in existing_rows:
            ver_row = existing_rows["_settings_version"]
            try:
                next_version = int(ver_row.value or 0) + 1
            except (ValueError, TypeError):
                next_version = 1
            ver_row.value = str(next_version)
            ver_row.updated_at = now
            ver_row.updated_by = user_id
        else:
            next_version = 1
            ver_row = SystemSetting(
                key="_settings_version",
                value="1",
                category="system",
                description="系统配置持久化版本号",
                is_secret=False,
                updated_at=now,
                updated_by=user_id,
            )
            self.session.add(ver_row)

        await self.session.commit()

        # 6. 从数据库重新全量读取同一份快照并提取版本号，触发本地原子热更新
        stmt_all = select(SystemSetting)
        res_all = await self.session.execute(stmt_all)
        db_all = {r.key: r.value for r in res_all.scalars().all()}
        committed_version = int(db_all.get("_settings_version") or next_version)
        apply_system_settings_override(db_all, version=committed_version)

        # 7. 跨进程版本同步：广播至 Redis 运行态（以 DB 事实源为准，容忍 Redis 异常）
        try:
            from app.services.redis_runtime_client import get_redis_runtime_client

            runtime = get_redis_runtime_client()
            runtime.set(runtime.key("system_settings:version"), str(committed_version))
        except Exception:
            pass

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


async def load_system_settings_on_startup(session: AsyncSession) -> tuple[bool, int]:
    """应用启动或重载时从数据库加载系统设置并应用覆盖层，安全容错。返回 (成功状态, 生效版本)。"""
    try:
        stmt = select(SystemSetting)
        result = await session.execute(stmt)
        rows = result.scalars().all()
        if rows:
            db_map = {row.key: row.value for row in rows}
            db_version = int(db_map.get("_settings_version") or 1)
            apply_system_settings_override(db_map, version=db_version)
            logger.info("已从数据库加载并生效 %d 项系统设置（版本 %d）。", len(db_map), db_version)
            return True, db_version
        return True, 0
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "应用启动加载系统设置失败（表可能未就绪），保持默认配置继续运行: %s",
            exc,
            extra={"event": "system_settings.startup_load_failed"},
        )
        return False, 0


async def run_system_settings_version_sync_loop(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """后台轮询系统设置版本，确保多副本 Backend 即时同步并热更新配置。"""
    from app.core.config import get_local_settings_version, set_local_settings_version
    from app.services.redis_runtime_client import get_redis_runtime_client

    tick = 0
    while True:
        try:
            tick += 1
            need_sync = False
            remote_ver: int | None = None

            # 1. 优先尝试从 Redis 读取远端版本号（非单调假设，凡不一致均视作需同步）
            try:
                runtime = get_redis_runtime_client()
                remote_ver_str = runtime.get(runtime.key("system_settings:version"))
                if remote_ver_str is not None:
                    remote_ver = int(remote_ver_str)
                    if remote_ver != get_local_settings_version():
                        need_sync = True
            except Exception:
                pass

            # 2. Redis 异常兜底或周期性 DB 对账（每 10 秒即 5 次循环检查一次 DB 持久化版本）
            if not need_sync and (remote_ver is None or tick % 5 == 0):
                async with session_factory() as check_session:
                    stmt = select(SystemSetting.value).where(SystemSetting.key == "_settings_version")
                    db_ver_val = (await check_session.execute(stmt)).scalar_one_or_none()
                    if db_ver_val is not None:
                        db_ver = int(db_ver_val)
                        if db_ver != get_local_settings_version():
                            need_sync = True

            # 3. 若发现不一致，从数据库加载最新快照；仅在加载成功后确认版本推进
            if need_sync:
                async with session_factory() as reload_session:
                    ok, loaded_ver = await load_system_settings_on_startup(reload_session)
                    if ok:
                        set_local_settings_version(loaded_ver)
                        # 补偿机制：若 Redis 暂无数据或落后，主动写回 Redis
                        try:
                            runtime = get_redis_runtime_client()
                            runtime.set(runtime.key("system_settings:version"), str(loaded_ver))
                        except Exception:
                            pass
        except asyncio.CancelledError:
            break
        except Exception:
            pass
        await asyncio.sleep(2)

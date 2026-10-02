"""文件功能：定义系统设置项元数据规格（Spec），约束各设置项分类、类型、默认值、校验规则与脱敏逻辑。"""

from collections.abc import Callable
from dataclasses import dataclass
import os
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class SystemSettingSpec:
    """系统配置规格定义。

    职责：
    - 约束设置项所属分类（category）、数据类型、是否敏感凭证；
    - 提供出厂默认值与校验逻辑；
    - 提供敏感数据掩码方法。
    """

    key: str
    category: str  # storage / general / security / ai / diagnostic
    description: str
    value_type: type
    default_value: Any
    is_secret: bool = False
    validator: Callable[[Any], Any] | None = None

    def mask_value(self, value: Any) -> Any:
        """为敏感数据生成掩码展示，非敏感数据返回原值。"""
        if not self.is_secret or value is None:
            return value
        text = str(value).strip()
        if not text:
            return ""
        return "******"


def _validate_timezone(value: Any) -> str:
    """校验业务时区合法性。"""
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("APP_TIMEZONE 不能为空。")
    try:
        ZoneInfo(normalized)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"时区配置无效：{normalized}") from exc
    return normalized


def _validate_storage_driver(value: Any) -> str:
    """校验存储驱动枚举。"""
    normalized = str(value or "").strip().lower()
    if normalized not in {"local", "s3"}:
        raise ValueError(f"存储驱动仅支持 local 或 s3，收到：{value}")
    return normalized


def _validate_log_level(value: Any) -> str:
    """校验日志级别枚举。"""
    normalized = str(value or "").strip().upper()
    if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError(f"日志级别仅支持 DEBUG, INFO, WARNING, ERROR, CRITICAL，收到：{value}")
    return normalized


def _validate_ai_image_transport_mode(value: Any) -> str:
    """校验 AI 图片传输模式。"""
    normalized = str(value or "").strip().lower()
    if normalized == "s3":
        normalized = "url"
    elif normalized == "data_url":
        normalized = "base64"
    if normalized not in {"auto", "url", "base64"}:
        raise ValueError(f"AI 图片传输模式仅支持 auto, url, base64，收到：{value}")
    return normalized


def _validate_positive_int(min_val: int = 1, max_val: int = 100000) -> Callable[[Any], int]:
    """生成正整数校验器。"""

    def _validator(value: Any) -> int:
        try:
            parsed = int(value)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"必须是整数，收到：{value}") from exc
        if parsed < min_val or parsed > max_val:
            raise ValueError(f"值必须在 {min_val} 到 {max_val} 之间，收到：{parsed}")
        return parsed

    return _validator


def _validate_positive_float(min_val: float = 0.1, max_val: float = 86400.0) -> Callable[[Any], float]:
    """生成正浮点数校验器。"""

    def _validator(value: Any) -> float:
        try:
            parsed = float(value)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"必须是浮点数，收到：{value}") from exc
        if parsed < min_val or parsed > max_val:
            raise ValueError(f"值必须在 {min_val} 到 {max_val} 之间，收到：{parsed}")
        return parsed

    return _validator


def _validate_non_empty_str(value: Any) -> str:
    """校验非空字符串。"""
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("配置项不能为空。")
    return normalized


def _validate_optional_str(value: Any) -> str | None:
    """规范化可选字符串，空字符串转为 None。"""
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _validate_bool(value: Any) -> bool:
    """规范化并严格校验布尔值，杜绝未知字符串被隐式转换为 True。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        raise ValueError(f"数值 {value!r} 不是合法的布尔标识（必须为 0 或 1）。")
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
        raise ValueError(f"无法将文本 {value!r} 解析为合法布尔值，合法值为 true/false、1/0、yes/no、on/off。")
    raise ValueError(f"不支持的布尔值类型：{type(value).__name__}。")


# 类 B 配置项规格字典（19 项）
SYSTEM_SETTING_SPECS: dict[str, SystemSettingSpec] = {
    # 存储配置
    "asset_storage_driver": SystemSettingSpec(
        key="asset_storage_driver",
        category="storage",
        description="对象资产存储驱动，支持 local 或 s3",
        value_type=str,
        default_value="local",
        validator=_validate_storage_driver,
    ),
    "s3_endpoint_url": SystemSettingSpec(
        key="s3_endpoint_url",
        category="storage",
        description="S3 兼容存储 Endpoint 地址（留空使用默认 AWS S3）",
        value_type=str,
        default_value=None,
        validator=_validate_optional_str,
    ),
    "s3_access_key": SystemSettingSpec(
        key="s3_access_key",
        category="storage",
        description="S3 访问密钥 ID（Access Key）",
        value_type=str,
        default_value=None,
        is_secret=True,
        validator=_validate_optional_str,
    ),
    "s3_secret_key": SystemSettingSpec(
        key="s3_secret_key",
        category="storage",
        description="S3 访问私钥（Secret Key）",
        value_type=str,
        default_value=None,
        is_secret=True,
        validator=_validate_optional_str,
    ),
    "s3_bucket": SystemSettingSpec(
        key="s3_bucket",
        category="storage",
        description="S3 主存储桶名称",
        value_type=str,
        default_value=None,
        validator=_validate_optional_str,
    ),
    "s3_public_bucket": SystemSettingSpec(
        key="s3_public_bucket",
        category="storage",
        description="S3 公开存储桶名称（留空使用主桶）",
        value_type=str,
        default_value=None,
        validator=_validate_optional_str,
    ),
    "s3_region": SystemSettingSpec(
        key="s3_region",
        category="storage",
        description="S3 区域（Region）",
        value_type=str,
        default_value=None,
        validator=_validate_optional_str,
    ),
    "s3_public_base_url": SystemSettingSpec(
        key="s3_public_base_url",
        category="storage",
        description="S3 公共可访问基址 CDN/URL",
        value_type=str,
        default_value=None,
        validator=_validate_optional_str,
    ),
    # 常规设置
    "app_name": SystemSettingSpec(
        key="app_name",
        category="general",
        description="平台品牌与系统显示名称",
        value_type=str,
        default_value="页面管理后台",
        validator=_validate_non_empty_str,
    ),
    "app_timezone": SystemSettingSpec(
        key="app_timezone",
        category="general",
        description="平台业务时区（例如 Asia/Shanghai）",
        value_type=str,
        default_value="Asia/Shanghai",
        validator=_validate_timezone,
    ),
    # 安全策略
    "session_ttl_hours": SystemSettingSpec(
        key="session_ttl_hours",
        category="security",
        description="用户会话有效期（小时）",
        value_type=int,
        default_value=24,
        validator=_validate_positive_int(1, 8760),
    ),
    "pat_max_active_tokens": SystemSettingSpec(
        key="pat_max_active_tokens",
        category="security",
        description="单用户个人访问令牌（PAT）最大活跃数量",
        value_type=int,
        default_value=25,
        validator=_validate_positive_int(1, 1000),
    ),
    "pat_max_ttl_days": SystemSettingSpec(
        key="pat_max_ttl_days",
        category="security",
        description="个人访问令牌（PAT）最长有效期（天）",
        value_type=int,
        default_value=365,
        validator=_validate_positive_int(1, 3650),
    ),
    # AI 运营
    "ai_enabled": SystemSettingSpec(
        key="ai_enabled",
        category="ai",
        description="AI 智能体助手全局总开关",
        value_type=bool,
        default_value=True,
        validator=_validate_bool,
    ),
    "ai_model_catalog_sync_enabled": SystemSettingSpec(
        key="ai_model_catalog_sync_enabled",
        category="ai",
        description="Models.dev 模型目录自动同步开关",
        value_type=bool,
        default_value=True,
        validator=_validate_bool,
    ),
    "ai_image_transport_mode": SystemSettingSpec(
        key="ai_image_transport_mode",
        category="ai",
        description="AI 图片传输与预览模式（auto / url / base64）",
        value_type=str,
        default_value="auto",
        validator=_validate_ai_image_transport_mode,
    ),
    "ai_agent_stream_idle_timeout_seconds": SystemSettingSpec(
        key="ai_agent_stream_idle_timeout_seconds",
        category="ai",
        description="AI 流式生成无响应空闲超时时间（秒）",
        value_type=float,
        default_value=180.0,
        validator=_validate_positive_float(1.0, 3600.0),
    ),
    # 系统诊断
    "log_level": SystemSettingSpec(
        key="log_level",
        category="diagnostic",
        description="系统运行时日志级别（DEBUG / INFO / WARNING / ERROR / CRITICAL）",
        value_type=str,
        default_value="INFO",
        validator=_validate_log_level,
    ),
    "ai_llm_http_trace_enabled": SystemSettingSpec(
        key="ai_llm_http_trace_enabled",
        category="diagnostic",
        description="大模型 HTTP 请求抓包与调试追踪开关",
        value_type=bool,
        default_value=False,
        validator=_validate_bool,
    ),
}


def is_env_overridden(key: str) -> bool:
    """检查指定配置项是否被系统环境变量或 .env 显式覆盖（非空）。

    契约规定：生效配置 = 环境变量 (ENV 覆盖) ≻ 数据库 Web UI 配置 ≻ 代码默认常量。
    如果系统环境变量或任何生效的 .env 文件中存在且非空，返回 True，表示环境强制覆盖生效。
    """
    env_name = key.upper()
    val = os.environ.get(env_name)
    if val is not None and val.strip() != "":
        return True

    from app.core.config import _iter_settings_env_files

    import dotenv

    for env_path in _iter_settings_env_files():
        try:
            values = dotenv.dotenv_values(env_path)
            for k, v in values.items():
                if k and k.upper() == env_name and v is not None and str(v).strip() != "":
                    return True
        except Exception:
            continue
    return False


def safe_mode_convert_value(key: str, raw_value: Any) -> tuple[Any, str | None]:
    """对原始值进行 Safe-Mode 校验与类型转换。

    返回 (converted_value, error_message)。
    若成功，error_message 为 None；
    若失败，converted_value 为 Spec 默认值，error_message 为错误原因。
    """
    spec = SYSTEM_SETTING_SPECS.get(key)
    if not spec:
        return raw_value, f"未知配置项：{key}"

    if raw_value is None:
        if spec.default_value is None:
            return None, None
        return spec.default_value, None

    try:
        if spec.validator:
            converted = spec.validator(raw_value)
        elif spec.value_type is bool:
            converted = _validate_bool(raw_value)
        elif spec.value_type is int:
            converted = int(raw_value)
        elif spec.value_type is float:
            converted = float(raw_value)
        else:
            converted = str(raw_value)
        return converted, None
    except Exception as exc:  # noqa: BLE001
        return spec.default_value, str(exc)

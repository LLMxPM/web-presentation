"""文件功能：定义素材基础地址与读取票据类型的单一判定规则，供预览上下文签发时显式声明。"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

AssetBaseUrlAuth = Literal["preview_token", "none"]

# 平台受保护预览素材前缀：`{public_base}/preview/artifacts/{artifact_id}/assets`
PROTECTED_PREVIEW_ASSET_PATH_MARKER = "/preview/artifacts/"


def resolve_asset_base_url_auth(asset_base_url: str | None) -> AssetBaseUrlAuth:
    """解析素材基础地址所需的读取票据类型。

    预览素材是否需要附带预览票据由 Backend 在签发上下文时显式声明
    （`asset_base_url_auth`），运行时只做查表，不再对拼接后的资源路径做子串推断。

    Args:
        asset_base_url: 本次 artifact 的素材基础地址。

    Returns:
        `preview_token`：平台受保护预览素材入口，浏览器读取必须附带预览票据；
        `none`：其余形态（如构建快照或本地 fixture 地址）不需要附带票据。
    """

    path = urlsplit(str(asset_base_url or "").strip()).path
    normalized = path.rstrip("/")
    if PROTECTED_PREVIEW_ASSET_PATH_MARKER in normalized and normalized.endswith("/assets"):
        return "preview_token"
    return "none"

"""文件功能：提供用户文件与素材受保护访问鉴权、快照成员校验、条件请求处理与 Range 解析。"""

from __future__ import annotations

import mimetypes
import re
import urllib.parse
from typing import Any

from fastapi import Request
import jwt

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.services.token_service import TokenService

# 业务错误码定义（与实施规划第 257-268 行保持一致）
FILE_ACCESS_REQUIRED = "FILE_ACCESS_REQUIRED"
FILE_ACCESS_INVALID = "FILE_ACCESS_INVALID"
FILE_ACCESS_EXPIRED = "FILE_ACCESS_EXPIRED"
FILE_ACCESS_SCOPE_MISMATCH = "FILE_ACCESS_SCOPE_MISMATCH"
FILE_NOT_FOUND = "FILE_NOT_FOUND"
PREVIEW_ARTIFACT_EXPIRED = "PREVIEW_ARTIFACT_EXPIRED"

NO_STORE_HEADERS = {"Cache-Control": "no-store"}


class FileAuthService:
    """提供用户文件与受保护素材访问的凭证校验、范围判定与 HTTP 缓存响应协议。"""

    @staticmethod
    def extract_token_from_request(request: Request) -> str | None:
        """从请求查询参数或 Authorization 头中提取访问令牌。

        Args:
            request: FastAPI 请求对象。

        Returns:
            提取到的令牌字符串；未携带时返回 None。
        """

        token = request.query_params.get("token")
        if token and str(token).strip():
            return str(token).strip()

        auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth_header:
            parts = auth_header.strip().split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                return parts[1].strip()

        return None

    @classmethod
    def verify_preview_asset_access(
        cls,
        *,
        request: Request,
        artifact_id: str,
        file_hash: str,
        manifest: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """校验浏览器预览素材请求的凭证有效性及快照资源归属。

        严格按照：验证凭证 -> 检查有效期 -> 校验 artifact 归属 -> 校验快照成员 的顺序执行。

        Args:
            request: HTTP 请求。
            artifact_id: 路径中的目标 artifact ID。
            file_hash: 请求的文件内容 SHA256 哈希。
            manifest: 目标 artifact 的 manifest 快照。

        Returns:
            已验签的 Token Claims 载荷。

        Raises:
            AppException: 凭证缺失、无效、过期、范围不符或资源未在快照中声明时抛出。
        """

        token = cls.extract_token_from_request(request)
        if not token:
            raise AppException(
                status_code=401,
                code=FILE_ACCESS_REQUIRED,
                detail="缺少预览素材访问凭证。",
                headers=NO_STORE_HEADERS,
            )

        try:
            claims = TokenService.verify_signed_token(token, audience="runtime-preview")
        except jwt.ExpiredSignatureError as exc:
            raise AppException(
                status_code=401,
                code=FILE_ACCESS_EXPIRED,
                detail="预览凭证已过期。",
                headers=NO_STORE_HEADERS,
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise AppException(
                status_code=401,
                code=FILE_ACCESS_INVALID,
                detail="预览凭证无效或无法验签。",
                headers=NO_STORE_HEADERS,
            ) from exc

        token_artifact_id = str(claims.get("artifact_id") or "").strip()
        if token_artifact_id != str(artifact_id).strip():
            raise AppException(
                status_code=403,
                code=FILE_ACCESS_SCOPE_MISMATCH,
                detail="预览凭证与目标 artifact 不匹配。",
                headers=NO_STORE_HEADERS,
            )

        if manifest is None:
            raise AppException(
                status_code=410,
                code=PREVIEW_ARTIFACT_EXPIRED,
                detail="预览 artifact 已过期或不存在。",
                headers=NO_STORE_HEADERS,
            )

        if not cls.is_hash_in_manifest(manifest, file_hash):
            raise AppException(
                status_code=404,
                code=FILE_NOT_FOUND,
                detail="请求的资源不在本次预览快照中。",
                headers=NO_STORE_HEADERS,
            )

        return claims

    @classmethod
    def verify_internal_asset_access(
        cls,
        *,
        request: Request,
        artifact_id: str,
        file_hash: str,
        manifest: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """校验 Runtime 或构建 Worker 内部回源读取素材的服务凭证。

        Args:
            request: HTTP 请求。
            artifact_id: 路径中的目标 artifact ID。
            file_hash: 请求的文件内容 SHA256 哈希。
            manifest: 目标 artifact 的 manifest 快照。

        Returns:
            已验签的 Token Claims 载荷。

        Raises:
            AppException: 服务凭证缺失、无效、用途不符或资源未在快照中时抛出。
        """

        token = cls.extract_token_from_request(request)
        if not token:
            raise AppException(
                status_code=401,
                code=FILE_ACCESS_REQUIRED,
                detail="缺少内部回源访问凭证。",
                headers=NO_STORE_HEADERS,
            )

        claims: dict[str, Any] | None = None
        settings = get_settings()

        # 尝试使用 Runtime 服务票据验签
        try:
            claims = TokenService.verify_signed_token(token, audience=settings.runtime_service_token_audience)
        except Exception:  # noqa: BLE001
            claims = None

        # 尝试使用构建命令令牌验签
        if claims is None:
            try:
                claims = TokenService.verify_runtime_build_command_token(token)
            except Exception:  # noqa: BLE001
                claims = None

        if claims is None:
            raise AppException(
                status_code=401,
                code=FILE_ACCESS_INVALID,
                detail="内部回源访问凭证无效或已过期。",
                headers=NO_STORE_HEADERS,
            )

        token_artifact_id = str(claims.get("artifact_id") or "").strip()
        if token_artifact_id != str(artifact_id).strip():
            raise AppException(
                status_code=403,
                code=FILE_ACCESS_SCOPE_MISMATCH,
                detail="内部服务凭证与目标 artifact 不匹配。",
                headers=NO_STORE_HEADERS,
            )

        if manifest is None:
            raise AppException(
                status_code=410,
                code=PREVIEW_ARTIFACT_EXPIRED,
                detail="预览 artifact 已过期或不存在。",
                headers=NO_STORE_HEADERS,
            )

        if not cls.is_hash_in_manifest(manifest, file_hash):
            raise AppException(
                status_code=404,
                code=FILE_NOT_FOUND,
                detail="请求的资源不在本次快照中。",
                headers=NO_STORE_HEADERS,
            )

        return claims

    @staticmethod
    def is_hash_in_manifest(manifest: dict[str, Any], file_hash: str) -> bool:
        """检查文件哈希是否被包含在 artifact manifest 的合法资源集合中。

        Args:
            manifest: 预览快照 manifest。
            file_hash: 待检查的文件 hash。

        Returns:
            若在合法快照集合中返回 True，否则返回 False。
        """

        target = str(file_hash).strip().lower()
        if not target:
            return False

        # 1. 检查 assets 映射（key 为逻辑路径或文件名，value 为 hash 或对象）
        assets = manifest.get("assets")
        if isinstance(assets, dict):
            for key, val in assets.items():
                if str(key).strip().lower() == target:
                    return True
                if isinstance(val, str) and val.strip().lower() == target:
                    return True
                if isinstance(val, dict) and str(val.get("file_hash") or "").strip().lower() == target:
                    return True
        elif isinstance(assets, list):
            for item in assets:
                if isinstance(item, str) and item.strip().lower() == target:
                    return True
                if isinstance(item, dict) and str(item.get("file_hash") or "").strip().lower() == target:
                    return True

        # 2. 检查 asset_metadata 映射
        asset_metadata = manifest.get("asset_metadata")
        if isinstance(asset_metadata, dict):
            for key, val in asset_metadata.items():
                if str(key).strip().lower() == target:
                    return True
                if isinstance(val, dict) and str(val.get("file_hash") or "").strip().lower() == target:
                    return True

        return False

    @staticmethod
    def evaluate_preconditions(request: Request, etag: str) -> bool:
        """评估 HTTP 条件请求头（If-None-Match），判定是否可直接返回 304。

        Args:
            request: FastAPI 请求对象。
            etag: 目标资源实际计算得出的强/弱 ETag。

        Returns:
            若条件匹配可返回 304 Not Modified 则为 True，否则为 False。
        """

        if_none_match = request.headers.get("if-none-match")
        if not if_none_match:
            return False

        normalized_target = etag.strip('"').removeprefix("W/").strip('"')
        for item in if_none_match.split(","):
            raw_val = item.strip().strip('"').removeprefix("W/").strip('"')
            if raw_val == "*" or raw_val == normalized_target:
                return True

        return False

    @staticmethod
    def parse_single_range(range_header: str | None, total_size: int) -> tuple[int, int] | None:
        """解析单段 Range 请求头，并验证边界有效性。

        Args:
            range_header: 客户端传入的 Range 请求头字符串。
            total_size: 文件总字节大小。

        Returns:
            若存在有效单段 Range 返回包含闭区间端点的 (start, end) 元组；若无 Range 返回 None。

        Raises:
            AppException: 当 Range 格式非法或超出文件范围时抛出 416 异常。
        """

        if not range_header or not range_header.strip():
            return None

        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
        if not match:
            raise AppException(
                status_code=416,
                code="RANGE_NOT_SATISFIABLE",
                detail="无法满足的 Range 请求头格式。",
                headers={"Content-Range": f"bytes */{total_size}", **NO_STORE_HEADERS},
            )

        start_str, end_str = match.groups()
        if not start_str and not end_str:
            raise AppException(
                status_code=416,
                code="RANGE_NOT_SATISFIABLE",
                detail="无效的空 Range 范围。",
                headers={"Content-Range": f"bytes */{total_size}", **NO_STORE_HEADERS},
            )

        if start_str and not end_str:
            start = int(start_str)
            end = total_size - 1
        elif not start_str and end_str:
            suffix_len = int(end_str)
            if suffix_len == 0:
                raise AppException(
                    status_code=416,
                    code="RANGE_NOT_SATISFIABLE",
                    detail="后缀长度必须大于零。",
                    headers={"Content-Range": f"bytes */{total_size}", **NO_STORE_HEADERS},
                )
            start = max(0, total_size - suffix_len)
            end = total_size - 1
        else:
            start = int(start_str)
            end = int(end_str)

        if total_size == 0 or start < 0 or start > end or start >= total_size:
            raise AppException(
                status_code=416,
                code="RANGE_NOT_SATISFIABLE",
                detail="请求的 Range 范围超出文件实际大小。",
                headers={"Content-Range": f"bytes */{total_size}", **NO_STORE_HEADERS},
            )

        end = min(end, total_size - 1)
        return (start, end)

    @staticmethod
    def build_protected_headers(
        *,
        etag: str,
        total_size: int,
        range_span: tuple[int, int] | None = None,
        is_download: bool = False,
        original_name: str | None = None,
    ) -> dict[str, str]:
        """构建私有受保护静态资源的标准化 HTTP 响应头。

        遵循实施规划：默认 private, no-cache，配合 ETag，禁止跨用户/共享缓存。

        Args:
            etag: 资源内容 ETag。
            total_size: 完整资源字节大小。
            range_span: 若为分段响应则传入 (start, end)。
            is_download: 是否指示浏览器触发下载。
            original_name: 下载时的原始文件名。

        Returns:
            标准 HTTP 响应头字典。
        """

        headers: dict[str, str] = {
            "Cache-Control": "private, no-cache",
            "ETag": f'"{etag}"',
            "Accept-Ranges": "bytes",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Access-Control-Allow-Origin": "*",
        }

        if range_span is not None:
            start, end = range_span
            headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"
            headers["Content-Length"] = str(end - start + 1)
        else:
            headers["Content-Length"] = str(total_size)

        if is_download and original_name:
            encoded_name = urllib.parse.quote(original_name)
            headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_name}"

        return headers

    @classmethod
    async def serve_protected_artifact_asset(
        cls,
        *,
        request: Request,
        artifact_id: str,
        file_hash: str,
        claims: dict[str, Any],
        manifest: dict[str, Any],
        session: Any,
        is_download: bool = False,
        is_head: bool = False,
    ) -> Any:
        """统一交付受保护的预览/内部素材内容，处理条件请求与 Range 切片。

        Args:
            request: HTTP 请求。
            artifact_id: 预览 artifact ID。
            file_hash: 目标素材 hash。
            claims: 已验签的访问载荷。
            manifest: 预览快照 manifest。
            session: AsyncSession 数据库会话。
            is_download: 是否触发附件下载。
            is_head: 是否为 HEAD 请求。

        Returns:
            FileResponse 或 Response 响应。
        """

        from fastapi.responses import FileResponse, Response
        from app.services.asset_service import AssetService
        from app.services.runtime_artifact_store import RuntimeArtifactStore

        # 1. 优先检查是否为模板包临时预览 blob 资源
        blob = await RuntimeArtifactStore().get_asset_blob(artifact_id, file_hash)
        if blob is not None:
            content = blob["content"]
            media_type = str(blob.get("content_type") or "application/octet-stream")
            original_name = str(blob.get("original_name") or f"{file_hash}.bin")
            total_size = len(content)
            etag = file_hash

            if cls.evaluate_preconditions(request, etag):
                return Response(
                    status_code=304,
                    headers=cls.build_protected_headers(etag=etag, total_size=total_size),
                )

            range_span = cls.parse_single_range(request.headers.get("range"), total_size)
            headers = cls.build_protected_headers(
                etag=etag,
                total_size=total_size,
                range_span=range_span,
                is_download=is_download,
                original_name=original_name,
            )

            if is_head:
                return Response(status_code=200 if range_span is None else 206, media_type=media_type, headers=headers)

            if range_span is not None:
                start, end = range_span
                return Response(
                    content=content[start : end + 1],
                    status_code=206,
                    media_type=media_type,
                    headers=headers,
                )
            return Response(content=content, status_code=200, media_type=media_type, headers=headers)

        # 2. 从快照与声明中读取工作空间资产
        owner_scope = manifest.get("owner_scope")
        workspace_id_raw: Any = None
        if isinstance(owner_scope, dict):
            workspace_id_raw = owner_scope.get("workspace_id")
        if workspace_id_raw is None:
            workspace_id_raw = claims.get("workspace_id")

        if not workspace_id_raw:
            raise AppException(
                status_code=404,
                code=FILE_NOT_FOUND,
                detail="无法确定素材所属工作空间。",
                headers=NO_STORE_HEADERS,
            )

        workspace_id = int(str(workspace_id_raw).strip())
        asset_service = AssetService(session)
        asset, driver = await asset_service.get_asset_by_hash(workspace_id, file_hash)

        media_type, _ = mimetypes.guess_type(asset.original_name)
        resolved_media_type = asset.content_type or media_type or "application/octet-stream"
        etag = asset.file_hash
        total_size = asset.file_size

        if cls.evaluate_preconditions(request, etag):
            return Response(
                status_code=304,
                headers=cls.build_protected_headers(etag=etag, total_size=total_size),
            )

        range_span = cls.parse_single_range(request.headers.get("range"), total_size)
        headers = cls.build_protected_headers(
            etag=etag,
            total_size=total_size,
            range_span=range_span,
            is_download=is_download,
            original_name=asset.original_name,
        )

        if is_head:
            return Response(status_code=200 if range_span is None else 206, media_type=resolved_media_type, headers=headers)

        async with driver.open_for_read(
            workspace_id,
            asset.file_name,
            expected_sha256=asset.file_hash,
            expected_size=asset.file_size,
        ) as local_file_path:
            if range_span is not None:
                start, end = range_span
                with open(local_file_path, "rb") as f:
                    f.seek(start)
                    chunk = f.read(end - start + 1)
                return Response(
                    content=chunk,
                    status_code=206,
                    media_type=resolved_media_type,
                    headers=headers,
                )

            # 无 Range 时以二进制直接返回
            with open(local_file_path, "rb") as f:
                content = f.read()
            return Response(
                content=content,
                status_code=200,
                media_type=resolved_media_type,
                headers=headers,
            )


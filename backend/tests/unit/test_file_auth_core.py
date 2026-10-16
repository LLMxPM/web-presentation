"""文件功能：测试受保护文件访问授权核心服务，包括各类令牌校验、快照成员检查、ETag 条件请求与 Range 处理。"""

import pytest
from unittest.mock import Mock
from starlette.requests import Request

from app.core.exceptions import AppException
from app.services.file_auth_service import (
    FILE_ACCESS_EXPIRED,
    FILE_ACCESS_INVALID,
    FILE_ACCESS_REQUIRED,
    FILE_ACCESS_SCOPE_MISMATCH,
    FILE_NOT_FOUND,
    PREVIEW_ARTIFACT_EXPIRED,
    FileAuthService,
)
from app.services.token_service import TokenService


def _create_mock_request(
    query_params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> Request:
    """构造测试用模拟 Request 对象。"""

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/test",
        "headers": [(k.lower().encode("latin1"), v.encode("latin1")) for k, v in (headers or {}).items()],
        "query_string": "&".join(f"{k}={v}" for k, v in (query_params or {}).items()).encode("latin1"),
    }
    return Request(scope)


def test_extract_token_from_query_and_header():
    """验证从 query 参数与 Authorization 头中提取令牌的优先级与逻辑。"""

    # 1. 从 query 提取
    req1 = _create_mock_request(query_params={"token": "token-from-query"})
    assert FileAuthService.extract_token_from_request(req1) == "token-from-query"

    # 2. 从 header 提取
    req2 = _create_mock_request(headers={"Authorization": "Bearer token-from-header"})
    assert FileAuthService.extract_token_from_request(req2) == "token-from-header"

    # 3. query 优先于 header
    req3 = _create_mock_request(
        query_params={"token": "query-tok"},
        headers={"Authorization": "Bearer header-tok"},
    )
    assert FileAuthService.extract_token_from_request(req3) == "query-tok"

    # 4. 无 token
    req4 = _create_mock_request()
    assert FileAuthService.extract_token_from_request(req4) is None


def test_verify_preview_asset_access_missing_token():
    """验证缺少预览凭证时返回 401 FILE_ACCESS_REQUIRED 与 no-store 响应头。"""

    req = _create_mock_request()
    with pytest.raises(AppException) as exc_info:
        FileAuthService.verify_preview_asset_access(
            request=req,
            artifact_id="art-123",
            file_hash="hash-abc",
            manifest={"assets": {}},
        )
    assert exc_info.value.status_code == 401
    assert exc_info.value.code == FILE_ACCESS_REQUIRED
    assert exc_info.value.headers == {"Cache-Control": "no-store"}


def test_verify_preview_asset_access_invalid_and_expired_token():
    """验证无效令牌与过期令牌的错误码区分。"""

    # 1. 伪造/无效令牌
    req_inv = _create_mock_request(query_params={"token": "invalid.jwt.token"})
    with pytest.raises(AppException) as exc_info:
        FileAuthService.verify_preview_asset_access(
            request=req_inv,
            artifact_id="art-123",
            file_hash="hash-abc",
            manifest={"assets": {}},
        )
    assert exc_info.value.status_code == 401
    assert exc_info.value.code == FILE_ACCESS_INVALID

    # 2. 已过期令牌
    expired_token = TokenService.generate_preview_context_token(
        artifact_id="art-123",
        preview_kind="project",
        scope_type="project",
        workspace_id=1,
        entry_descriptor={"entry_type": "route", "route": "/"},
        asset_base_url="/assets",
        trace_id="tr-1",
        tenant_id="tenant_1",
        expires_in_seconds=-10,
    )
    req_exp = _create_mock_request(query_params={"token": expired_token})
    with pytest.raises(AppException) as exc_info:
        FileAuthService.verify_preview_asset_access(
            request=req_exp,
            artifact_id="art-123",
            file_hash="hash-abc",
            manifest={"assets": {}},
        )
    assert exc_info.value.status_code == 401
    assert exc_info.value.code == FILE_ACCESS_EXPIRED


def test_verify_preview_asset_access_scope_mismatch():
    """验证跨 artifact 访问时拒绝并返回 403 FILE_ACCESS_SCOPE_MISMATCH。"""

    valid_token = TokenService.generate_preview_context_token(
        artifact_id="art-123",
        preview_kind="project",
        scope_type="project",
        workspace_id=1,
        entry_descriptor={"entry_type": "route", "route": "/"},
        asset_base_url="/assets",
        trace_id="tr-1",
        tenant_id="tenant_1",
        expires_in_seconds=300,
    )
    req = _create_mock_request(query_params={"token": valid_token})

    with pytest.raises(AppException) as exc_info:
        FileAuthService.verify_preview_asset_access(
            request=req,
            artifact_id="different-art-456",
            file_hash="hash-abc",
            manifest={"assets": {}},
        )
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == FILE_ACCESS_SCOPE_MISMATCH


def test_verify_preview_asset_access_artifact_expired():
    """验证 artifact 已过期不存在时返回 410 PREVIEW_ARTIFACT_EXPIRED。"""

    valid_token = TokenService.generate_preview_context_token(
        artifact_id="art-123",
        preview_kind="project",
        scope_type="project",
        workspace_id=1,
        entry_descriptor={"entry_type": "route", "route": "/"},
        asset_base_url="/assets",
        trace_id="tr-1",
        tenant_id="tenant_1",
        expires_in_seconds=300,
    )
    req = _create_mock_request(query_params={"token": valid_token})

    with pytest.raises(AppException) as exc_info:
        FileAuthService.verify_preview_asset_access(
            request=req,
            artifact_id="art-123",
            file_hash="hash-abc",
            manifest=None,
        )
    assert exc_info.value.status_code == 410
    assert exc_info.value.code == PREVIEW_ARTIFACT_EXPIRED


def test_verify_preview_asset_access_not_in_manifest():
    """验证请求快照范围以外的素材时返回 404 FILE_NOT_FOUND。"""

    valid_token = TokenService.generate_preview_context_token(
        artifact_id="art-123",
        preview_kind="project",
        scope_type="project",
        workspace_id=1,
        entry_descriptor={"entry_type": "route", "route": "/"},
        asset_base_url="/assets",
        trace_id="tr-1",
        tenant_id="tenant_1",
        expires_in_seconds=300,
    )
    req = _create_mock_request(query_params={"token": valid_token})
    manifest = {
        "assets": {"logo.png": "hash-legit-123"},
        "asset_metadata": {},
    }

    with pytest.raises(AppException) as exc_info:
        FileAuthService.verify_preview_asset_access(
            request=req,
            artifact_id="art-123",
            file_hash="hash-unauthorized-999",
            manifest=manifest,
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == FILE_NOT_FOUND


def test_verify_preview_asset_access_success():
    """验证在快照中的合法素材成功返回 claims。"""

    valid_token = TokenService.generate_preview_context_token(
        artifact_id="art-123",
        preview_kind="project",
        scope_type="project",
        workspace_id=1,
        entry_descriptor={"entry_type": "route", "route": "/"},
        asset_base_url="/assets",
        trace_id="tr-1",
        tenant_id="tenant_1",
        expires_in_seconds=300,
    )
    req = _create_mock_request(query_params={"token": valid_token})
    manifest = {
        "assets": {"icons/star.svg": "hash-legit-123"},
        "asset_metadata": {},
    }

    claims = FileAuthService.verify_preview_asset_access(
        request=req,
        artifact_id="art-123",
        file_hash="hash-legit-123",
        manifest=manifest,
    )
    assert claims["artifact_id"] == "art-123"
    assert claims["workspace_id"] == "1"


def test_evaluate_preconditions_etag():
    """测试 If-None-Match 条件请求对强/弱 ETag 和星号通配的匹配。"""

    # 1. 匹配强 ETag
    req1 = _create_mock_request(headers={"If-None-Match": '"abc12345"'})
    assert FileAuthService.evaluate_preconditions(req1, "abc12345") is True

    # 2. 匹配弱 ETag
    req2 = _create_mock_request(headers={"If-None-Match": 'W/"abc12345"'})
    assert FileAuthService.evaluate_preconditions(req2, "abc12345") is True

    # 3. 匹配星号通配
    req3 = _create_mock_request(headers={"If-None-Match": "*"})
    assert FileAuthService.evaluate_preconditions(req3, "abc12345") is True

    # 4. 不匹配
    req4 = _create_mock_request(headers={"If-None-Match": '"xyz789"'})
    assert FileAuthService.evaluate_preconditions(req4, "abc12345") is False

    # 5. 无 If-None-Match
    req5 = _create_mock_request()
    assert FileAuthService.evaluate_preconditions(req5, "abc12345") is False


def test_parse_single_range():
    """测试单段 Range 请求解析与边界异常校验。"""

    total_size = 1000

    # 1. bytes=0-499
    assert FileAuthService.parse_single_range("bytes=0-499", total_size) == (0, 499)

    # 2. bytes=500- (从 500 到文件末尾)
    assert FileAuthService.parse_single_range("bytes=500-", total_size) == (500, 999)

    # 3. bytes=-200 (末尾 200 字节)
    assert FileAuthService.parse_single_range("bytes=-200", total_size) == (800, 999)

    # 4. 无 Range
    assert FileAuthService.parse_single_range(None, total_size) is None
    assert FileAuthService.parse_single_range("", total_size) is None

    # 5. 非法格式或多段（首期仅支持单段）
    with pytest.raises(AppException) as exc1:
        FileAuthService.parse_single_range("bytes=0-10,20-30", total_size)
    assert exc1.value.status_code == 416

    # 6. 超出总大小
    with pytest.raises(AppException) as exc2:
        FileAuthService.parse_single_range("bytes=1500-2000", total_size)
    assert exc2.value.status_code == 416

    # 7. start > end
    with pytest.raises(AppException) as exc3:
        FileAuthService.parse_single_range("bytes=500-300", total_size)
    assert exc3.value.status_code == 416


def test_build_protected_headers():
    """测试生成受保护资源的 HTTP 响应头。"""

    headers = FileAuthService.build_protected_headers(
        etag="my-etag-123",
        total_size=1024,
        range_span=(0, 511),
        is_download=True,
        original_name="测试图片.png",
    )
    assert headers["Cache-Control"] == "private, no-cache"
    assert headers["ETag"] == '"my-etag-123"'
    assert headers["Content-Range"] == "bytes 0-511/1024"
    assert headers["Content-Length"] == "512"
    assert "attachment; filename*=UTF-8''" in headers["Content-Disposition"]


def test_generate_signed_token_overwrites_security_claims():
    """验证 generate_signed_token 强制覆盖 payload 中伪造的安全保留声明。"""
    payload = {
        "iss": "attacker",
        "exp": 9999999999,
        "iat": 1000,
        "custom_key": "custom_val",
    }
    token = TokenService.generate_signed_token(
        payload,
        expires_in_seconds=60,
        issuer="backend",
    )
    claims = TokenService.verify_signed_token(token)
    assert claims["iss"] == "backend"
    assert claims["custom_key"] == "custom_val"
    assert claims["exp"] < 9000000000  # 伪造的远期 exp 已被覆盖并按入参生效


def test_verify_internal_asset_access_expired():
    """验证内部回源凭证过期时准确返回 FILE_ACCESS_EXPIRED。"""
    expired_token = TokenService.generate_signed_token(
        {"artifact_id": "art-1", "aud": "runtime-service"},
        expires_in_seconds=-10,  # 已过期
    )
    request = _create_mock_request(headers={"Authorization": f"Bearer {expired_token}"})
    with pytest.raises(AppException) as exc:
        FileAuthService.verify_internal_asset_access(
            request=request,
            artifact_id="art-1",
            file_hash="hash-1",
            manifest={"assets": {"test.png": "hash-1"}},
        )
    assert exc.value.status_code == 401
    assert exc.value.code == "FILE_ACCESS_EXPIRED"


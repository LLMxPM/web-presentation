"""文件功能：验证签名身份共享加载、多副本禁止自动生成与密钥轮换期旧票据行为。"""

from __future__ import annotations

from pathlib import Path

import jwt
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import AppSettings
from app.services.signing_identity import (
    SigningIdentityError,
    load_signing_keyring,
    validate_shared_identity_deployment,
)
from app.services.token_service import TokenService

# 多实例校验要求合法且非占位的 Fernet 密钥。
_VALID_AI_SECRET_KEY = Fernet.generate_key().decode("utf-8")


def _generate_pem_key_pair() -> tuple[bytes, bytes]:
    """生成一对测试用 RSA 私钥/公钥 PEM。"""

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def _write_key(path: Path) -> bytes:
    """写入一把新的测试私钥，返回其 PEM 内容。"""

    private_pem, _public_pem = _generate_pem_key_pair()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(private_pem)
    return private_pem


def _settings(tmp_path: Path, **overrides: object) -> AppSettings:
    """构造不读取仓库 .env 的测试配置，默认单实例本地存储。"""

    base: dict[str, object] = {
        "_env_file": None,
        "page_screenshot_local_root": str(tmp_path / "data"),
        "asset_storage_driver": "local",
        "redis_url": "redis://127.0.0.1:6379/0",
        "runtime_rsa_private_key": "",
        "runtime_rsa_private_key_file": None,
        "runtime_rsa_key_id": "default-key-1",
        "runtime_rsa_previous_keys": [],
        "runtime_rsa_allow_auto_generate": True,
        "backend_multi_instance": False,
        "object_storage_shared_volume": False,
        # 显式固定，避免 os.environ 里其它用例写入的 AI_SECRET_ENCRYPTION_KEY 造成污染。
        "ai_secret_encryption_key": _VALID_AI_SECRET_KEY,
        "default_admin_password": "StrongTestAdminPass#2026!",
        "runtime_build_worker_credential": "StrongTestBuildCred#2026!",
        "render_service_credential": "StrongTestRenderSecret#2026!",
    }
    base.update(overrides)
    return AppSettings(**base)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _reset_token_service() -> None:
    """每个用例后清空 TokenService 进程内密钥缓存，避免跨用例串钥。"""

    TokenService.reset_signing_keyring()
    yield
    TokenService.reset_signing_keyring()


def test_multi_instance_should_share_same_signing_identity(tmp_path: Path) -> None:
    """两个 Backend 实例读取同一共享私钥时，彼此签发的票据可以互相验签。"""

    shared_key = tmp_path / "shared" / "runtime_rsa_key.pem"
    _write_key(shared_key)

    instance_a = _settings(
        tmp_path,
        backend_multi_instance=True,
        asset_storage_driver="s3",
        runtime_rsa_private_key_file=str(shared_key),
    )
    instance_b = _settings(
        tmp_path,
        backend_multi_instance=True,
        asset_storage_driver="s3",
        runtime_rsa_private_key_file=str(shared_key),
    )

    keyring_a = load_signing_keyring(instance_a)
    keyring_b = load_signing_keyring(instance_b)
    assert keyring_a.signing.kid == keyring_b.signing.kid == "default-key-1"
    assert (
        keyring_a.signing.public_key.public_numbers().n
        == keyring_b.signing.public_key.public_numbers().n
    )

    # 实例 A 签发，实例 B 校验（模拟请求落到另一副本）。
    TokenService.reset_signing_keyring()
    TokenService._keyring = keyring_a  # type: ignore[attr-defined]
    token = TokenService.generate_signed_token(
        {"aud": "runtime-preview", "artifact_id": "a1"},
        expires_in_seconds=300,
    )
    TokenService.reset_signing_keyring()
    TokenService._keyring = keyring_b  # type: ignore[attr-defined]
    claims = TokenService.verify_signed_token(token, audience="runtime-preview")
    assert claims["artifact_id"] == "a1"


def test_multi_instance_should_reject_auto_generated_keys(tmp_path: Path) -> None:
    """多 Backend 模式禁止各副本自动生成本地私钥，必须显式提供共享密钥来源。"""

    settings = _settings(tmp_path, backend_multi_instance=True, asset_storage_driver="s3")
    with pytest.raises(SigningIdentityError, match="共享"):
        load_signing_keyring(settings)
    assert not (tmp_path / "data" / "runtime_rsa_key.pem").exists()


def test_multi_instance_should_reject_local_object_storage_without_shared_volume(tmp_path: Path) -> None:
    """多 Backend 使用本地对象存储时，必须显式确认共享卷或改用 S3。"""

    shared_key = tmp_path / "shared" / "key.pem"
    _write_key(shared_key)
    shared_secrets = {
        "ai_secret_encryption_key": _VALID_AI_SECRET_KEY,
        "render_service_credential": "a-strong-shared-render-secret",
    }
    local_only = _settings(
        tmp_path,
        backend_multi_instance=True,
        asset_storage_driver="local",
        runtime_rsa_private_key_file=str(shared_key),
        **shared_secrets,
    )
    with pytest.raises(SigningIdentityError, match="共享对象存储"):
        validate_shared_identity_deployment(local_only)

    acknowledged = _settings(
        tmp_path,
        backend_multi_instance=True,
        asset_storage_driver="local",
        object_storage_shared_volume=True,
        runtime_rsa_private_key_file=str(shared_key),
        **shared_secrets,
    )
    validate_shared_identity_deployment(acknowledged)


def test_multi_instance_should_reject_placeholder_shared_secrets(tmp_path: Path) -> None:
    """多 Backend 下 AI 凭证加密密钥与 Renderer 服务凭证禁止默认/占位值。"""

    shared_key = tmp_path / "shared" / "key.pem"
    _write_key(shared_key)

    default_ai = _settings(
        tmp_path,
        backend_multi_instance=True,
        asset_storage_driver="s3",
        runtime_rsa_private_key_file=str(shared_key),
        ai_secret_encryption_key="vmgRweOsDpMtYVW7SSpceINYcXlUHFNndAby6vRv0iA=",
    )
    with pytest.raises(SigningIdentityError, match="AI_SECRET_ENCRYPTION_KEY"):
        validate_shared_identity_deployment(default_ai)

    placeholder_render = _settings(
        tmp_path,
        backend_multi_instance=True,
        asset_storage_driver="s3",
        runtime_rsa_private_key_file=str(shared_key),
        ai_secret_encryption_key=_VALID_AI_SECRET_KEY,
        render_service_credential="change-me",
    )
    with pytest.raises(SigningIdentityError, match="RENDER_SERVICE_CREDENTIAL"):
        validate_shared_identity_deployment(placeholder_render)


def test_single_instance_should_reject_placeholder_secrets(tmp_path: Path) -> None:
    """单实例/Lite 也不得照抄 compose 示例弱密钥启动（P1-Secrets / CFG1a）。"""

    settings = _settings(
        tmp_path,
        ai_secret_encryption_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )
    with pytest.raises(SigningIdentityError, match="AI_SECRET_ENCRYPTION_KEY"):
        validate_shared_identity_deployment(settings)

    # 包含模板大写下划线与默认口令
    for bad_pwd in ["change-admin-password", "REPLACE_WITH_STRONG_PASSWORD", "Admin123456", "admin"]:
        weak_admin = _settings(
            tmp_path,
            ai_secret_encryption_key=_VALID_AI_SECRET_KEY,
            default_admin_password=bad_pwd,
        )
        with pytest.raises(SigningIdentityError, match="DEFAULT_ADMIN_PASSWORD"):
            validate_shared_identity_deployment(weak_admin)

    # 包含模板大写下划线与 shared secret 占位
    for bad_cred in ["change-build-worker-credential", "REPLACE_WITH_STRONG_BUILD_CREDENTIAL", "replace-with-strong-shared-secret"]:
        weak_build = _settings(
            tmp_path,
            ai_secret_encryption_key=_VALID_AI_SECRET_KEY,
            runtime_build_worker_credential=bad_cred,
        )
        with pytest.raises(SigningIdentityError, match="RUNTIME_BUILD_WORKER_CREDENTIAL"):
            validate_shared_identity_deployment(weak_build)

    for bad_render in ["change-me-render-secret", "REPLACE_WITH_STRONG_RENDER_SECRET", "replace-with-strong-shared-secret"]:
        weak_render = _settings(
            tmp_path,
            ai_secret_encryption_key=_VALID_AI_SECRET_KEY,
            render_service_credential=bad_render,
        )
        with pytest.raises(SigningIdentityError, match="RENDER_SERVICE_CREDENTIAL"):
            validate_shared_identity_deployment(weak_render)


def test_single_instance_may_auto_generate_ai_secret_key(tmp_path: Path) -> None:
    """单实例缺省 AI 加密密钥时自动生成持久化密钥，重启后保持一致（CFG1）。"""

    settings = _settings(tmp_path, ai_secret_encryption_key="")
    validate_shared_identity_deployment(settings)
    key_file = tmp_path / "data" / "ai_secret.key"
    assert key_file.is_file()
    generated_key = key_file.read_text(encoding="utf-8").strip()
    assert settings.ai_secret_encryption_key == generated_key
    assert len(generated_key) == 44

    # 重启读取持久化文件，不生成新密钥
    reloaded_settings = _settings(tmp_path, ai_secret_encryption_key="")
    validate_shared_identity_deployment(reloaded_settings)
    assert reloaded_settings.ai_secret_encryption_key == generated_key


def test_multi_instance_must_fail_closed_on_missing_ai_secret_key(tmp_path: Path) -> None:
    """多 Backend 部署缺省 AI 加密密钥时禁止自动生成，必须 fail-closed（CFG1）。"""

    shared_key = tmp_path / "shared" / "runtime_rsa_key.pem"
    _write_key(shared_key)
    settings = _settings(
        tmp_path,
        backend_multi_instance=True,
        asset_storage_driver="s3",
        runtime_rsa_private_key_file=str(shared_key),
        ai_secret_encryption_key="",
    )
    with pytest.raises(SigningIdentityError, match="AI_SECRET_ENCRYPTION_KEY"):
        validate_shared_identity_deployment(settings)


def test_single_instance_may_auto_generate_local_key(tmp_path: Path) -> None:
    """单实例缺省配置仍可自动生成本地私钥，保持 Lite/开发体验不变。"""

    settings = _settings(tmp_path)
    keyring = load_signing_keyring(settings)
    assert keyring.signing.source == "generated"
    assert (tmp_path / "data" / "runtime_rsa_key.pem").is_file()

    # 同一实例重启后读取既有文件，不再生成新钥。
    reloaded = load_signing_keyring(_settings(tmp_path))
    assert reloaded.signing.source == "legacy-file"
    assert (
        reloaded.signing.public_key.public_numbers().n
        == keyring.signing.public_key.public_numbers().n
    )


def test_rotation_keeps_old_tickets_valid_within_ttl(tmp_path: Path) -> None:
    """轮换后旧钥保留在验签环中时，TTL 内旧票据仍有效；移除旧钥后立即失效。"""

    old_key_path = tmp_path / "keys" / "default-key-1.pem"
    new_key_path = tmp_path / "keys" / "default-key-2.pem"
    _write_key(old_key_path)
    _write_key(new_key_path)

    old_settings = _settings(
        tmp_path,
        runtime_rsa_private_key_file=str(old_key_path),
        runtime_rsa_key_id="default-key-1",
    )
    TokenService._keyring = load_signing_keyring(old_settings)  # type: ignore[attr-defined]
    old_token = TokenService.generate_signed_token(
        {"aud": "runtime-preview", "artifact_id": "old-1"},
        expires_in_seconds=300,
    )
    old_header = jwt.get_unverified_header(old_token)
    assert old_header["kid"] == "default-key-1"

    rotated_settings = _settings(
        tmp_path,
        runtime_rsa_private_key_file=str(new_key_path),
        runtime_rsa_key_id="default-key-2",
        runtime_rsa_previous_keys=[
            {"kid": "default-key-1", "private_key_file": str(old_key_path)},
        ],
    )
    TokenService._keyring = load_signing_keyring(rotated_settings)  # type: ignore[attr-defined]

    # 旧票据在 TTL 内仍可验证。
    claims = TokenService.verify_signed_token(old_token, audience="runtime-preview")
    assert claims["artifact_id"] == "old-1"

    # 新票据使用新 kid，旧票据仍可并存。
    new_token = TokenService.generate_signed_token(
        {"aud": "runtime-preview", "artifact_id": "new-1"},
        expires_in_seconds=300,
    )
    assert jwt.get_unverified_header(new_token)["kid"] == "default-key-2"
    assert TokenService.verify_signed_token(new_token, audience="runtime-preview")["artifact_id"] == "new-1"

    # JWKS 同时公布新旧公钥，Runtime 可据此验证任一时期的票据。
    jwks_kids = {item["kid"] for item in TokenService.get_jwks()["keys"]}
    assert jwks_kids == {"default-key-1", "default-key-2"}

    # 轮换完成、旧钥移出验签环后，旧票据立即失效（明确的失效策略）。
    finished_settings = _settings(
        tmp_path,
        runtime_rsa_private_key_file=str(new_key_path),
        runtime_rsa_key_id="default-key-2",
    )
    TokenService._keyring = load_signing_keyring(finished_settings)  # type: ignore[attr-defined]
    with pytest.raises(jwt.PyJWTError):
        TokenService.verify_signed_token(old_token, audience="runtime-preview")


def test_rotation_rejects_expired_old_tickets(tmp_path: Path) -> None:
    """即使旧钥仍在验签环中，超过自身 TTL 的旧票据必须按 exp 拒绝。"""

    old_key_path = tmp_path / "keys" / "old.pem"
    new_key_path = tmp_path / "keys" / "new.pem"
    _write_key(old_key_path)
    _write_key(new_key_path)

    old_settings = _settings(
        tmp_path,
        runtime_rsa_private_key_file=str(old_key_path),
        runtime_rsa_key_id="old-kid",
    )
    TokenService._keyring = load_signing_keyring(old_settings)  # type: ignore[attr-defined]
    expired_token = TokenService.generate_signed_token(
        {"aud": "runtime-preview", "artifact_id": "expired"},
        expires_in_seconds=-10,
    )

    rotated_settings = _settings(
        tmp_path,
        runtime_rsa_private_key_file=str(new_key_path),
        runtime_rsa_key_id="new-kid",
        runtime_rsa_previous_keys=[{"kid": "old-kid", "private_key_file": str(old_key_path)}],
    )
    TokenService._keyring = load_signing_keyring(rotated_settings)  # type: ignore[attr-defined]
    with pytest.raises(jwt.ExpiredSignatureError):
        TokenService.verify_signed_token(expired_token, audience="runtime-preview")


def test_previous_key_kid_must_not_collide_with_signing_kid(tmp_path: Path) -> None:
    """轮换期旧钥 kid 与当前签名 kid 冲突时启动失败，避免 JWKS 条目歧义。"""

    key_path = tmp_path / "keys" / "only.pem"
    _write_key(key_path)
    settings = _settings(
        tmp_path,
        runtime_rsa_private_key_file=str(key_path),
        runtime_rsa_key_id="default-key-1",
        runtime_rsa_previous_keys=[{"kid": "default-key-1", "private_key_file": str(key_path)}],
    )
    with pytest.raises(SigningIdentityError, match="冲突"):
        load_signing_keyring(settings)


def test_inline_env_pem_is_shared_signing_source(tmp_path: Path) -> None:
    """环境变量内联 PEM 可作为多 Backend 共享签名来源，两个实例互通。"""

    private_pem, _ = _generate_pem_key_pair()
    settings_a = _settings(
        tmp_path,
        backend_multi_instance=True,
        asset_storage_driver="s3",
        runtime_rsa_private_key=private_pem.decode("utf-8"),
    )
    settings_b = _settings(
        tmp_path,
        backend_multi_instance=True,
        asset_storage_driver="s3",
        runtime_rsa_private_key=private_pem.decode("utf-8"),
    )
    keyring_a = load_signing_keyring(settings_a)
    keyring_b = load_signing_keyring(settings_b)
    assert keyring_a.signing.source == "env"
    assert (
        keyring_a.signing.public_key.public_numbers().n
        == keyring_b.signing.public_key.public_numbers().n
    )

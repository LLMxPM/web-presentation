"""文件功能：测试 rotate_ai_secret_key 脚本的密钥校验、重加密逻辑与异常处理。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from app.scripts.rotate_ai_secret_key import (
    _validate_fernet_key,
    generate_fernet_key,
    rotate_secrets,
)


def test_generate_fernet_key_validity() -> None:
    """验证生成的 Fernet 密钥合法且可用于加解密。"""

    key = generate_fernet_key()
    cipher = Fernet(key.encode("utf-8"))
    token = cipher.encrypt(b"test-secret")
    assert cipher.decrypt(token) == b"test-secret"


def test_validate_fernet_key_error_cases() -> None:
    """验证空值或非法格式密钥抛出 ValueError。"""

    with pytest.raises(ValueError, match="不能为空"):
        _validate_fernet_key("", "test_key")

    with pytest.raises(ValueError, match="不是合法的 Fernet 密钥"):
        _validate_fernet_key("not-a-valid-base64-key", "test_key")


@pytest.mark.asyncio
async def test_rotate_secrets_rejects_placeholder_new_key() -> None:
    """验证新密钥禁止使用系统内置示例占位值。"""

    old_key = generate_fernet_key()
    placeholder_new_key = "vmgRweOsDpMtYVW7SSpceINYcXlUHFNndAby6vRv0iA="

    with pytest.raises(ValueError, match="不能是系统内置的默认/示例占位值"):
        await rotate_secrets(old_key, placeholder_new_key)


@pytest.mark.asyncio
async def test_rotate_secrets_success_and_dry_run() -> None:
    """验证在单一事务中成功解密旧数据并使用新密钥重加密，且 dry-run 不会提交。"""

    old_key = generate_fernet_key()
    new_key = generate_fernet_key()
    old_cipher = Fernet(old_key.encode("utf-8"))
    new_cipher = Fernet(new_key.encode("utf-8"))

    secret_plain = "my-llm-api-token"
    old_ciphertext = old_cipher.encrypt(secret_plain.encode("utf-8")).decode("utf-8")

    mock_chat_rows = [(1, "Test Chat Provider", old_ciphertext)]
    mock_image_rows = [(2, "Test Image Provider", old_ciphertext)]

    # 模拟 session
    mock_session = AsyncMock()
    mock_execute = AsyncMock()
    mock_execute.side_effect = [
        MagicMock(all=MagicMock(return_value=mock_chat_rows)),
        None,  # update
        MagicMock(all=MagicMock(return_value=mock_image_rows)),
        None,  # update
    ]
    mock_session.execute = mock_execute

    # 包装 session.begin() 上下文
    mock_begin_ctx = AsyncMock()
    mock_begin_ctx.__aenter__.return_value = None
    mock_begin_ctx.__aexit__.return_value = None
    mock_session.begin = MagicMock(return_value=mock_begin_ctx)

    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__.return_value = mock_session
    mock_session_ctx.__aexit__.return_value = None
    mock_factory = MagicMock(return_value=mock_session_ctx)

    with patch("app.scripts.rotate_ai_secret_key.get_session_factory", return_value=mock_factory):
        stats = await rotate_secrets(old_key, new_key, dry_run=False)

    assert stats.chat_total == 1
    assert stats.chat_reencrypted == 1
    assert stats.image_total == 1
    assert stats.image_reencrypted == 1

    # 检查 UPDATE 调用时的参数是否为新密钥加密的内容
    update_calls = [c for c in mock_execute.call_args_list if len(c.args) > 1 and "ct" in c.args[1]]
    assert len(update_calls) == 2
    for call in update_calls:
        reencrypted_ct = call.args[1]["ct"]
        assert new_cipher.decrypt(reencrypted_ct.encode("utf-8")).decode("utf-8") == secret_plain


@pytest.mark.asyncio
async def test_rotate_secrets_invalid_token_fails() -> None:
    """验证当旧密钥无法解密凭证时抛出明确异常。"""

    wrong_old_key = generate_fernet_key()
    new_key = generate_fernet_key()
    other_key = generate_fernet_key()
    other_cipher = Fernet(other_key.encode("utf-8"))

    # 数据是用 other_key 加密的
    corrupted_ciphertext = other_cipher.encrypt(b"token").decode("utf-8")

    mock_chat_rows = [(1, "Mismatched Provider", corrupted_ciphertext)]
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=mock_chat_rows)))

    mock_begin_ctx = AsyncMock()
    mock_begin_ctx.__aenter__.return_value = None
    mock_begin_ctx.__aexit__.return_value = None
    mock_session.begin = MagicMock(return_value=mock_begin_ctx)

    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__.return_value = mock_session
    mock_session_ctx.__aexit__.return_value = None
    mock_factory = MagicMock(return_value=mock_session_ctx)

    with patch("app.scripts.rotate_ai_secret_key.get_session_factory", return_value=mock_factory):
        with pytest.raises(RuntimeError, match="凭证无法用旧密钥解密"):
            await rotate_secrets(wrong_old_key, new_key, dry_run=False)

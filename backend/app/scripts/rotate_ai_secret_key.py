"""文件功能：在更换 AI_SECRET_ENCRYPTION_KEY 时平滑重加密数据库中所有已保存的聊天与生图供应商凭证。"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import NamedTuple

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services.signing_identity import _DEFAULT_AI_SECRET_ENCRYPTION_KEYS

logger = logging.getLogger(__name__)


class RotationStats(NamedTuple):
    """记录重加密执行统计。"""

    chat_total: int
    chat_reencrypted: int
    image_total: int
    image_reencrypted: int


def generate_fernet_key() -> str:
    """生成一个合法的 32 字节 Fernet 对称加密密钥。"""

    return Fernet.generate_key().decode("utf-8")


def _validate_fernet_key(key_str: str, key_name: str) -> Fernet:
    """验证传入的密钥是否为合法的 Fernet 密钥。"""

    normalized = (key_str or "").strip()
    if not normalized:
        raise ValueError(f"{key_name} 不能为空。")
    try:
        return Fernet(normalized.encode("utf-8"))
    except Exception as exc:
        raise ValueError(f"{key_name} 不是合法的 Fernet 密钥（需为 32 字节 URL-safe base64）。") from exc


async def rotate_secrets(
    old_key_str: str,
    new_key_str: str,
    *,
    dry_run: bool = False,
) -> RotationStats:
    """在单一事务内使用新密钥重新加密所有供应商凭证。

    :param old_key_str: 用于解密当前数据的旧密钥
    :param new_key_str: 用于重新加密数据的新密钥
    :param dry_run: 为 True 时仅做解密校验，不落库提交
    :return: 迁移统计数据
    """

    old_cipher = _validate_fernet_key(old_key_str, "old_key")
    new_cipher = _validate_fernet_key(new_key_str, "new_key")

    if new_key_str in _DEFAULT_AI_SECRET_ENCRYPTION_KEYS:
        raise ValueError("new_key 不能是系统内置的默认/示例占位值。")

    session_factory = get_session_factory()
    chat_reencrypted = 0
    image_reencrypted = 0

    async with session_factory() as session:
        async with session.begin():
            # 1. 迁移聊天供应商凭证 (ai_chat_provider_configs)
            chat_rows = (
                await session.execute(
                    text("SELECT id, name, api_key_ciphertext FROM ai_chat_provider_configs")
                )
            ).all()
            chat_total = len(chat_rows)

            for row_id, name, ciphertext in chat_rows:
                if not ciphertext:
                    continue
                try:
                    plaintext = old_cipher.decrypt(ciphertext.encode("utf-8"))
                except InvalidToken as exc:
                    raise RuntimeError(
                        f"聊天供应商 [{name}] (ID: {row_id}) 凭证无法用旧密钥解密，可能已被其他密钥加密。"
                    ) from exc

                new_ciphertext = new_cipher.encrypt(plaintext).decode("utf-8")
                if not dry_run:
                    await session.execute(
                        text(
                            "UPDATE ai_chat_provider_configs SET api_key_ciphertext = :ct WHERE id = :id"
                        ),
                        {"ct": new_ciphertext, "id": row_id},
                    )
                chat_reencrypted += 1

            # 2. 迁移生图供应商凭证 (ai_image_provider_configs)
            image_rows = (
                await session.execute(
                    text("SELECT id, name, api_key_ciphertext FROM ai_image_provider_configs")
                )
            ).all()
            image_total = len(image_rows)

            for row_id, name, ciphertext in image_rows:
                if not ciphertext:
                    continue
                try:
                    plaintext = old_cipher.decrypt(ciphertext.encode("utf-8"))
                except InvalidToken as exc:
                    raise RuntimeError(
                        f"生图供应商 [{name}] (ID: {row_id}) 凭证无法用旧密钥解密，可能已被其他密钥加密。"
                    ) from exc

                new_ciphertext = new_cipher.encrypt(plaintext).decode("utf-8")
                if not dry_run:
                    await session.execute(
                        text(
                            "UPDATE ai_image_provider_configs SET api_key_ciphertext = :ct WHERE id = :id"
                        ),
                        {"ct": new_ciphertext, "id": row_id},
                    )
                image_reencrypted += 1

            if dry_run:
                await session.rollback()

    return RotationStats(
        chat_total=chat_total,
        chat_reencrypted=chat_reencrypted,
        image_total=image_total,
        image_reencrypted=image_reencrypted,
    )


def main() -> None:
    """解析命令行参数并执行密钥平滑轮换。"""

    parser = argparse.ArgumentParser(
        description="平滑重加密数据库中所有已保存的聊天与生图供应商 API Key 凭证。"
    )
    parser.add_argument(
        "--old-key",
        default="",
        help="当前旧密钥；默认自动尝试读取当前应用配置或示例默认密钥。",
    )
    parser.add_argument(
        "--new-key",
        default="",
        help="待迁移的新密钥；若未指定且指定了 --generate-new-key 则自动生成。",
    )
    parser.add_argument(
        "--generate-new-key",
        action="store_true",
        help="自动生成一个随机的新 Fernet 密钥。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="演练模式：仅校验解密与加密流程，不将变更写入数据库。",
    )

    args = parser.parse_args()

    # 1. 解析旧密钥
    old_key = (args.old_key or "").strip()
    if not old_key:
        settings_key = (get_settings().ai_secret_encryption_key or "").strip()
        if settings_key:
            old_key = settings_key
        else:
            parser.error("未指定 --old-key 且当前配置中未包含旧密钥。")

    # 2. 解析新密钥
    new_key = (args.new_key or "").strip()
    if args.generate_new_key:
        if new_key:
            parser.error("--new-key 与 --generate-new-key 不能同时指定。")
        new_key = generate_fernet_key()
        print(f"已自动生成新密钥: {new_key}")
    elif not new_key:
        parser.error("请通过 --new-key 指定新密钥，或使用 --generate-new-key 自动生成。")

    if old_key == new_key:
        parser.error("新旧密钥相同，无需迁移。")

    print(f"准备开始密钥轮换{' (演练模式)' if args.dry_run else ''}...")
    try:
        stats = asyncio.run(rotate_secrets(old_key, new_key, dry_run=args.dry_run))
    except Exception as exc:
        print(f"\n[错误] 密钥轮换失败: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n==== 密钥轮换执行结果 ====")
    print(f"模式: {'DRY RUN (未写入数据库)' if args.dry_run else 'SUCCESS (已写入数据库)'}")
    print(f"聊天供应商: 共 {stats.chat_total} 项，成功重密 {stats.chat_reencrypted} 项凭证")
    print(f"生图供应商: 共 {stats.image_total} 项，成功重密 {stats.image_reencrypted} 项凭证")

    if not args.dry_run:
        print("\n后续操作提示:")
        print(f"1. 请将新密钥更新至 .env 文件中:\n   AI_SECRET_ENCRYPTION_KEY={new_key}")
        print("2. 重启平台后端服务，确认启动日志中无报错且供应商配置列表加载正常。")


if __name__ == "__main__":
    main()

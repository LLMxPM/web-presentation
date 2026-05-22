"""文件功能：封装密码哈希与会话令牌生成能力，供认证服务复用。"""

from hashlib import sha256
from secrets import token_urlsafe

from pwdlib import PasswordHash

_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """对明文密码进行安全哈希后返回持久化值。"""

    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """校验用户输入密码是否与数据库中的密码哈希匹配。"""

    return _password_hash.verify(password, password_hash)


def generate_session_token() -> str:
    """生成随机会话令牌，用于写入 HttpOnly Cookie。"""

    return token_urlsafe(48)


def hash_session_token(token: str) -> str:
    """对会话令牌做单向摘要，避免明文 token 落库。"""

    return sha256(token.encode("utf-8")).hexdigest()

"""文件功能：提供个人访问令牌（PAT）的安全审计与 Redis 双桶限速服务。"""

from __future__ import annotations

import logging

from app.core.exceptions import AppException
from app.services.redis_runtime_client import get_redis_runtime_client

logger = logging.getLogger(__name__)

# 限速参数常量
PAT_IP_RATE_LIMIT_MAX_REQUESTS = 60
PAT_IP_RATE_LIMIT_WINDOW_SECONDS = 60

PAT_AUTH_FAILURE_MAX_ATTEMPTS = 5
PAT_AUTH_FAILURE_WINDOW_SECONDS = 60
PAT_AUTH_FAILURE_LOCKOUT_SECONDS = 900  # 15 分钟临时封禁


class PatAuditService:
    """PAT 安全审计服务，记录脱敏后的令牌生命周期与鉴权事件。"""

    @staticmethod
    def log_token_created(*, user_id: int, token_id: int, public_id: str, name: str, ip: str | None = None) -> None:
        """记录 PAT 创建审计事件。"""

        logger.info(
            "PAT 访问令牌已创建。",
            extra={
                "event": "pat.created",
                "user_id": user_id,
                "token_id": token_id,
                "token_public_id": public_id,
                "token_name": name,
                "ip": ip or "unknown",
            },
        )

    @staticmethod
    def log_token_revoked(*, user_id: int, token_id: int, public_id: str, ip: str | None = None) -> None:
        """记录 PAT 吊销审计事件。"""

        logger.info(
            "PAT 访问令牌已吊销。",
            extra={
                "event": "pat.revoked",
                "user_id": user_id,
                "token_id": token_id,
                "token_public_id": public_id,
                "ip": ip or "unknown",
            },
        )

    @staticmethod
    def log_auth_failure(*, public_id: str | None, reason: str, ip: str | None = None) -> None:
        """记录 PAT 鉴权失败安全事件。"""

        logger.warning(
            "PAT 访问鉴权失败。",
            extra={
                "event": "pat.auth_failed",
                "token_public_id": public_id or "unknown",
                "reason": reason,
                "ip": ip or "unknown",
            },
        )

    @staticmethod
    def log_rate_limited(*, ip: str, public_id: str | None, lockout_seconds: int) -> None:
        """记录 PAT 限速触发事件。"""

        logger.warning(
            "PAT 鉴权触发失败限速封禁。",
            extra={
                "event": "pat.rate_limited",
                "ip": ip,
                "token_public_id": public_id or "unknown",
                "lockout_seconds": lockout_seconds,
            },
        )


class PatRateLimitService:
    """基于 Redis 的 PAT 双桶限速服务（支持 Redis 故障时的 Fail-Open 安全放行）。"""

    @classmethod
    def check_ip_rate_limit(cls, ip: str) -> None:
        """检查 IP 通用请求速率（60次/分）。"""

        if not ip or ip in {"127.0.0.1", "localhost", "::1"}:
            return

        try:
            redis = get_redis_runtime_client()
            key = redis.key(f"pat:rate_limit:ip:{ip}")
            current = redis.client.incr(key)
            if current == 1:
                redis.client.expire(key, PAT_IP_RATE_LIMIT_WINDOW_SECONDS)
            if current > PAT_IP_RATE_LIMIT_MAX_REQUESTS:
                ttl = redis.client.ttl(key) or PAT_IP_RATE_LIMIT_WINDOW_SECONDS
                raise AppException(
                    status_code=429,
                    code="RATE_LIMIT_EXCEEDED",
                    detail="请求过于频繁，请稍后再试。",
                    headers={"Retry-After": str(max(1, ttl))},
                )
        except AppException:
            raise
        except Exception as exc:
            logger.warning("PAT IP 限速检查 Redis 降级放行: %s", exc)

    @classmethod
    def check_auth_failure_rate_limit(cls, ip: str, public_id: str | None = None) -> None:
        """检查连续鉴权失败惩罚桶，超限时抛出 429 锁定。"""

        if not ip:
            return

        lock_key_suffix = f"pat:lockout:ip:{ip}"
        if public_id:
            lock_key_suffix += f":{public_id}"

        try:
            redis = get_redis_runtime_client()
            lock_key = redis.key(lock_key_suffix)
            is_locked = redis.client.get(lock_key)
            if is_locked:
                ttl = redis.client.ttl(lock_key) or PAT_AUTH_FAILURE_LOCKOUT_SECONDS
                PatAuditService.log_rate_limited(ip=ip, public_id=public_id, lockout_seconds=ttl)
                raise AppException(
                    status_code=429,
                    code="PAT_AUTH_RATE_LIMITED",
                    detail="认证失败次数过多，已被临时限制访问，请稍后再试。",
                    headers={"Retry-After": str(max(1, ttl))},
                )
        except AppException:
            raise
        except Exception as exc:
            logger.warning("PAT 封禁检查 Redis 降级放行: %s", exc)

    @classmethod
    def record_auth_failure(cls, ip: str, public_id: str | None = None) -> None:
        """记录一次鉴权失败；若达到阈值则触发 15 分钟封禁。"""

        if not ip:
            return

        bucket_key_suffix = f"pat:auth_fail:ip:{ip}"
        lock_key_suffix = f"pat:lockout:ip:{ip}"
        if public_id:
            bucket_key_suffix += f":{public_id}"
            lock_key_suffix += f":{public_id}"

        try:
            redis = get_redis_runtime_client()
            bucket_key = redis.key(bucket_key_suffix)
            lock_key = redis.key(lock_key_suffix)

            failures = redis.client.incr(bucket_key)
            if failures == 1:
                redis.client.expire(bucket_key, PAT_AUTH_FAILURE_WINDOW_SECONDS)

            if failures >= PAT_AUTH_FAILURE_MAX_ATTEMPTS:
                redis.client.set(lock_key, "1", ex=PAT_AUTH_FAILURE_LOCKOUT_SECONDS)
                redis.client.delete(bucket_key)
                PatAuditService.log_rate_limited(
                    ip=ip, public_id=public_id, lockout_seconds=PAT_AUTH_FAILURE_LOCKOUT_SECONDS
                )
        except Exception as exc:
            logger.warning("PAT 失败计数 Redis 降级: %s", exc)

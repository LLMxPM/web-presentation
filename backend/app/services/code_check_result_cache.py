"""文件功能：代码检查结果有界缓存与 in-flight 合并，按完整输入指纹复用稳定检查结果。"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# 编译器与检查规则版本：检查语义或判定规则变化时必须提升，使旧缓存整体失效。
CODE_CHECK_RULES_VERSION = "code-check-rules.v1"

# 默认有界容量与 TTL；调用方可按部署规模覆盖。
DEFAULT_MAX_ENTRIES = 256
DEFAULT_TTL_SECONDS = 600.0


@dataclass(slots=True)
class _CacheEntry:
    """缓存条目：结果载荷与写入时间。"""

    result: dict[str, object]
    stored_at: float


@dataclass(slots=True)
class CodeCheckCacheMetrics:
    """缓存命中率与容量指标，可直接读出。"""

    hits: int = 0
    misses: int = 0
    coalesced: int = 0
    stores: int = 0
    evictions: int = 0
    expired: int = 0
    skipped_transient: int = 0
    lookups: int = 0

    def snapshot(self, *, size: int, inflight: int) -> dict[str, int | float]:
        """导出指标快照并附带当前容量。"""

        total = self.hits + self.misses + self.coalesced
        hit_rate = round(self.hits / total, 4) if total else 0.0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "coalesced": self.coalesced,
            "stores": self.stores,
            "evictions": self.evictions,
            "expired": self.expired,
            "skipped_transient": self.skipped_transient,
            "lookups": self.lookups,
            "size": size,
            "inflight": inflight,
            "hit_rate": hit_rate,
        }


def is_transient_check_result(result: object) -> bool:
    """判断检查结果是否为瞬态基础设施失败。

    超时、Renderer 不可用、Runtime 不可用等结果不得作为稳定「代码检查失败」长期缓存。
    """

    if not isinstance(result, Mapping):
        return True
    if result.get("status") == "unavailable":
        return True
    if result.get("retryable") is True:
        return True
    stages = result.get("stages")
    if isinstance(stages, Mapping) and (
        stages.get("compile") == "unavailable" or stages.get("render") == "unavailable"
    ):
        return True
    diagnostics = result.get("diagnostics")
    if isinstance(diagnostics, list):
        for item in diagnostics:
            if isinstance(item, Mapping) and item.get("source") == "infrastructure":
                return True
    return False


def is_transient_infrastructure_error(exc: BaseException) -> bool:
    """判断异常是否属于瞬态基础设施故障（超时、502/503、Renderer 不可用）。"""

    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and status_code in {408, 425, 429, 500, 502, 503, 504}:
        return True
    code = str(getattr(exc, "code", "") or "")
    if code in {
        "RUNTIME_DIAGNOSTICS_FAILED",
        "RUNTIME_RESPONSE_INVALID",
        "RENDER_SERVICE_UNAVAILABLE",
        "PAGE_RENDER_DIAGNOSTICS_UNAVAILABLE",
        "COMPONENT_CHECK_UNAVAILABLE",
    }:
        return True
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return True
    module = type(exc).__module__ or ""
    return module.startswith("httpx") and "Timeout" in type(exc).__name__


def compute_check_fingerprint(payload: Mapping[str, Any]) -> str:
    """把完整输入指纹载荷压缩为稳定 SHA-256 指纹。"""

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


class CodeCheckResultCache:
    """有界 LRU + TTL 结果缓存，支持 in-flight 合并与命中率指标。"""

    def __init__(
        self,
        *,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries 必须为正数")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds 必须为正数")
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._inflight: dict[str, asyncio.Future[dict[str, object]]] = {}
        self._lock = asyncio.Lock()
        self._metrics = CodeCheckCacheMetrics()

    def snapshot_metrics(self) -> dict[str, int | float]:
        """读出命中率、容量与 in-flight 规模。"""

        return self._metrics.snapshot(size=len(self._entries), inflight=len(self._inflight))

    def clear(self) -> None:
        """清空缓存与指标，供测试与进程重置使用。"""

        self._entries.clear()
        self._inflight.clear()
        self._metrics = CodeCheckCacheMetrics()

    async def get_or_execute(
        self,
        fingerprint: str,
        factory: Callable[[], Awaitable[dict[str, object]]],
    ) -> tuple[dict[str, object], str]:
        """命中则复用；并发相同指纹合并为一次执行；仅缓存稳定结果。

        返回 (结果, 来源)，来源为 hit / miss / coalesced。鉴权必须在调用本方法之前完成。
        """

        async with self._lock:
            self._metrics.lookups += 1
            entry = self._get_valid_entry(fingerprint)
            if entry is not None:
                self._metrics.hits += 1
                self._maybe_log_metrics()
                return copy.deepcopy(entry.result), "hit"

            inflight = self._inflight.get(fingerprint)
            if inflight is not None:
                self._metrics.coalesced += 1
                waiter: asyncio.Future[dict[str, object]] | None = inflight
                owner = False
            else:
                waiter = asyncio.get_running_loop().create_future()
                self._inflight[fingerprint] = waiter
                self._metrics.misses += 1
                owner = True

        if not owner:
            assert waiter is not None
            result = await asyncio.shield(waiter)
            self._maybe_log_metrics()
            return copy.deepcopy(result), "coalesced"

        assert waiter is not None
        try:
            result = await factory()
            if is_transient_check_result(result):
                self._metrics.skipped_transient += 1
            else:
                self._store(fingerprint, result)
            if not waiter.done():
                waiter.set_result(result)
            self._maybe_log_metrics()
            return copy.deepcopy(result), "miss"
        except BaseException as exc:
            if not waiter.done():
                if isinstance(exc, Exception):
                    waiter.set_exception(exc)
                else:
                    waiter.set_exception(RuntimeError(f"代码检查执行中断：{exc!r}"))
                # 若最终没有 waiter 消费，预先取出异常以避免 asyncio 未检索告警。
                waiter.exception()
            # 异常一律不入缓存；瞬态基础设施错误尤其不得沉淀为稳定失败。
            raise
        finally:
            async with self._lock:
                if self._inflight.get(fingerprint) is waiter:
                    self._inflight.pop(fingerprint, None)

    def _get_valid_entry(self, fingerprint: str) -> _CacheEntry | None:
        """读取未过期条目并刷新 LRU 位置。"""

        entry = self._entries.get(fingerprint)
        if entry is None:
            return None
        if time.monotonic() - entry.stored_at > self.ttl_seconds:
            self._entries.pop(fingerprint, None)
            self._metrics.expired += 1
            return None
        self._entries.move_to_end(fingerprint)
        return entry

    def _store(self, fingerprint: str, result: dict[str, object]) -> None:
        """写入缓存并执行有界 LRU 淘汰。"""

        self._entries[fingerprint] = _CacheEntry(result=copy.deepcopy(result), stored_at=time.monotonic())
        self._entries.move_to_end(fingerprint)
        self._metrics.stores += 1
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)
            self._metrics.evictions += 1

    def _maybe_log_metrics(self) -> None:
        """按查表次数周期性输出命中率与容量，便于运维读出。"""

        if self._metrics.lookups % 50 != 0:
            return
        logger.info(
            "代码检查结果缓存指标。",
            extra={
                "event": "code_check.cache.metrics",
                **self.snapshot_metrics(),
            },
        )


_default_cache: CodeCheckResultCache | None = None


def get_code_check_result_cache() -> CodeCheckResultCache:
    """返回进程级默认代码检查结果缓存。"""

    global _default_cache
    if _default_cache is None:
        _default_cache = CodeCheckResultCache()
    return _default_cache


def reset_code_check_result_cache() -> None:
    """重置进程级默认缓存，供测试隔离与进程初始化使用。"""

    global _default_cache
    if _default_cache is not None:
        _default_cache.clear()
    _default_cache = None

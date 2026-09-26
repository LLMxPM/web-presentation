"""文件功能：Runtime 计算角色多副本选址与全链路准入，支持轮询、失败冷却和在途上限。

落点对应规划 T2-3：Backend 内部选址支持多计算实例/容量路由。不引入服务发现；
目标列表来自配置，选址仅做轮询 + 连续失败冷却，满载时切换其它空闲副本，
全部满载或本地准入超限时返回稳定可重试错误码。
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import httpx

from app.core.config import AppSettings, get_settings
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)

# 稳定容量错误码：客户端、AI 任务与结果缓存据此识别「可重试容量问题」而非业务失败。
RUNTIME_CAPACITY_EXCEEDED = "RUNTIME_CAPACITY_EXCEEDED"
RUNTIME_ADMISSION_FULL = "RUNTIME_ADMISSION_FULL"
RUNTIME_TARGETS_UNAVAILABLE = "RUNTIME_TARGETS_UNAVAILABLE"

# 满载/准入拒绝时的建议重试等待秒数，写入 Retry-After 供调用方退避。
RETRY_AFTER_SECONDS = "5"

# 判定为「目标满载」的 HTTP 状态码；命中后换副本重试，全部耗尽时映射为稳定容量错误。
_OVERLOAD_STATUS_CODES = {429, 503}

# 构建 POST 只有这些 Runtime 调度器错误能证明任务尚未开始执行，允许换副本。
# 其它 429/503 可能来自构建中的 Backend 回源或产物上传，结果必须视为不确定。
_BUILD_PRE_DISPATCH_CAPACITY_CODES = frozenset(
    {
        "RUNTIME_VITE_QUEUE_FULL",
        "RUNTIME_VITE_QUEUE_TIMEOUT",
        "RUNTIME_VITE_SCHEDULER_CLOSED",
    }
)

# 配置/鉴权类错误码：所有副本共享同一配置，换副本无意义；不得伪装成容量问题。
# 这类 503 必须保留真实错误码直接失败，避免配置事故烧光重试预算并呈现成扩容形状。
_CONFIG_OR_AUTH_ERROR_CODES = frozenset(
    {
        "JWKS_URL_MISSING",
        "JWKS_URL_INVALID",
        "BACKEND_API_BASE_URL_MISSING",
        "RUNTIME_SERVICE_TOKEN_REQUIRED",
        "RUNTIME_SERVICE_TOKEN_INVALID",
        "RUNTIME_PREVIEW_JWKS_URL_MISSING",
    }
)


def _extract_response_error_code(response: httpx.Response) -> str:
    """从 Runtime 错误响应中提取业务错误码；无法解析时返回空串。"""

    try:
        payload = response.json()
    except ValueError:
        return ""
    if isinstance(payload, dict):
        return str(payload.get("code") or "").strip()
    return ""


def _is_config_or_auth_error(response: httpx.Response) -> bool:
    """判断 503/错误响应是否为配置或鉴权故障（非容量满载）。"""

    return _extract_response_error_code(response) in _CONFIG_OR_AUTH_ERROR_CODES


@dataclass(slots=True)
class _TargetHealth:
    """单个选址目标的连续失败与冷却状态。"""

    consecutive_failures: int = 0
    cooldown_until: float = 0.0


class RuntimeTargetRouter:
    """Runtime build/check 多副本选址器：轮询 + 连续失败冷却 + 在途准入。

    - 选址顺序按轮询起点推进，冷却中的目标排到末尾作为兜底，避免全冷时黑洞。
    - 成功调用清零连续失败；连续失败达到阈值后短暂冷却，到期自动恢复。
    - 在途准入按角色计数，超限立即返回稳定错误，保护下游 Renderer/Preview 不被打穿。
    """

    def __init__(
        self,
        *,
        settings_provider: Callable[[], AppSettings] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._settings_provider = settings_provider or get_settings
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._rr_index: dict[str, int] = {}
        self._health: dict[tuple[str, str], _TargetHealth] = {}
        self._inflight: dict[str, int] = {}

    def ordered_candidates(self, role: str, targets: list[str]) -> list[str]:
        """返回本轮优先尝试的目标列表：轮询起点推进，冷却目标排后兜底。"""

        if not targets:
            return []
        with self._lock:
            index = self._rr_index.get(role, 0) % len(targets)
            self._rr_index[role] = index + 1
            rotated = targets[index:] + targets[:index]
            now = self._clock()
            ready = [target for target in rotated if not self._is_cooled_locked(role, target, now)]
            cooled = [target for target in rotated if self._is_cooled_locked(role, target, now)]
            return ready + cooled

    def mark_success(self, role: str, target: str) -> None:
        """目标调用成功：清零连续失败与冷却，重新参与轮询。"""

        with self._lock:
            health = self._health.get((role, target))
            if health is not None:
                health.consecutive_failures = 0
                health.cooldown_until = 0.0

    def mark_failure(self, role: str, target: str, *, overloaded: bool = False) -> None:
        """记录目标失败；连续失败达到阈值后进入短暂冷却。"""

        settings = self._settings_provider()
        threshold = int(settings.runtime_target_failure_threshold)
        cooldown_seconds = float(settings.runtime_target_cooldown_seconds)
        with self._lock:
            health = self._health.setdefault((role, target), _TargetHealth())
            health.consecutive_failures += 1
            consecutive = health.consecutive_failures
            if threshold > 0 and consecutive >= threshold and cooldown_seconds > 0:
                health.cooldown_until = self._clock() + cooldown_seconds
                logger.warning(
                    "Runtime 选址目标连续失败进入冷却。",
                    extra={
                        "event": "runtime.target.cooldown",
                        "role": role,
                        "target": target,
                        "consecutive_failures": consecutive,
                        "overloaded": overloaded,
                        "cooldown_seconds": cooldown_seconds,
                    },
                )

    def inflight_count(self, role: str) -> int:
        """读取角色当前在途调用数，便于测试与诊断。"""

        with self._lock:
            return self._inflight.get(role, 0)

    @contextmanager
    def admission(self, role: str) -> Iterator[None]:
        """全链路准入：在途调用达到角色上限时立即拒绝，避免打穿下游。

        check 与 light 各自独立计数：180 秒完整编译诊断不得把 10/40 秒轻量工具打成满载（M12）。
        """

        settings = self._settings_provider()
        if role == "build":
            max_inflight = int(settings.runtime_build_max_inflight)
        elif role == "light":
            # <=0 表示不限制（与配置说明一致），不得用 or 回退到 check 上限。
            max_inflight = int(settings.runtime_light_max_inflight)
        else:
            max_inflight = int(settings.runtime_check_max_inflight)
        with self._lock:
            current = self._inflight.get(role, 0)
            if max_inflight > 0 and current >= max_inflight:
                logger.warning(
                    "Runtime 角色在途调用已达准入上限。",
                    extra={
                        "event": "runtime.admission.rejected",
                        "role": role,
                        "inflight": current,
                        "max_inflight": max_inflight,
                    },
                )
                raise AppException(
                    status_code=503,
                    code=RUNTIME_ADMISSION_FULL,
                    detail=f"Runtime {role} 在途调用已达准入上限，请稍后重试。",
                    headers={"Retry-After": RETRY_AFTER_SECONDS},
                )
            self._inflight[role] = current + 1
        try:
            yield
        finally:
            with self._lock:
                self._inflight[role] = max(0, self._inflight.get(role, 0) - 1)

    def _is_cooled_locked(self, role: str, target: str, now: float) -> bool:
        """在持锁状态判断目标是否仍在冷却期。"""

        health = self._health.get((role, target))
        return health is not None and health.cooldown_until > now


_router_lock = threading.Lock()
_router: RuntimeTargetRouter | None = None


def get_runtime_target_router() -> RuntimeTargetRouter:
    """返回进程级选址器单例，跨请求共享轮询与冷却状态。"""

    global _router
    with _router_lock:
        if _router is None:
            _router = RuntimeTargetRouter()
        return _router


def _build_http_exception(
    response: httpx.Response,
    *,
    default_code: str,
    force_status_code: int | None = None,
    extra_data: dict[str, object] | None = None,
) -> AppException:
    """把 Runtime HTTP 错误响应归一为 AppException，保留上游业务码。"""

    code = default_code
    detail = response.text or "Runtime 请求失败。"
    try:
        payload = response.json()
        if isinstance(payload, dict):
            code = str(payload.get("code") or code)
            detail = str(payload.get("message") or payload.get("detail") or detail)
    except ValueError:
        pass
    return AppException(
        status_code=force_status_code or response.status_code,
        code=code,
        detail=detail,
        data=extra_data,
    )


async def request_runtime_role_json(
    *,
    role: str,
    method: str,
    path: str,
    settings: AppSettings,
    headers: dict[str, str],
    timeout_seconds: float,
    default_error_code: str,
    timeout_error_code: str | None = None,
    unavailable_error_code: str | None = None,
    invalid_response_code: str | None = None,
    content: bytes | None = None,
    json_payload: dict[str, object] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    router: RuntimeTargetRouter | None = None,
) -> dict[str, object]:
    """按角色选址调用 Runtime 内部 JSON 接口，满载自动换副本，全部耗尽返回稳定错误。

    - 构建 POST 只在连接未建立或明确的执行前容量拒绝时换副本。
    - 其它角色对连接失败、超时、5xx、429/503 尝试下一副本。
    - 其它 4xx：业务错误，直接抛出，不换副本。
    - 全部副本均满载：抛 RUNTIME_CAPACITY_EXCEEDED（503，可重试）。
    - 本地准入超限：抛 RUNTIME_ADMISSION_FULL（503，可重试），不发起下游调用。
    """

    active_router = router or get_runtime_target_router()
    targets = active_router.ordered_candidates(role, settings.resolve_runtime_role_base_urls(role))
    if not targets:
        raise AppException(
            status_code=503,
            code=RUNTIME_TARGETS_UNAVAILABLE,
            detail=f"Runtime {role} 未配置可用目标地址。",
            headers={"Retry-After": RETRY_AFTER_SECONDS},
        )

    last_error: AppException | None = None
    overload_seen = False
    with active_router.admission(role):
        for target in targets:
            try:
                async with httpx.AsyncClient(
                    base_url=target,
                    timeout=httpx.Timeout(timeout_seconds),
                    transport=transport,
                ) as client:
                    response = await client.request(
                        method,
                        path,
                        content=content,
                        json=json_payload,
                        headers=headers or {},
                    )
            except httpx.TimeoutException:
                active_router.mark_failure(role, target)
                last_error = AppException(
                    status_code=504,
                    code=timeout_error_code or default_error_code,
                    detail="Runtime 请求超时。",
                    data={"dispatch_may_have_started": True},
                )
                # 构建 POST 非幂等：超时后可能已在对端执行甚至已上传，禁止盲目换副本重发（M4）。
                # 超时交由租约/重试预算收敛，而不是再 POST 一份可能重复的构建。
                if role == "build" and method.upper() == "POST":
                    logger.error(
                        "Runtime 构建 POST 超时，不换副本重发非幂等请求。",
                        extra={
                            "event": "runtime.build.timeout_no_retry",
                            "role": role,
                            "target": target,
                            "path": path,
                        },
                    )
                    raise last_error
                logger.warning(
                    "Runtime 目标请求超时，尝试下一副本。",
                    extra={"event": "runtime.target.timeout", "role": role, "target": target, "path": path},
                )
                continue
            except httpx.ConnectError:
                # 连接未建立、请求未发出，可安全换副本。
                active_router.mark_failure(role, target)
                last_error = AppException(
                    status_code=502,
                    code=unavailable_error_code or default_error_code,
                    detail="Runtime 服务不可访问。",
                )
                logger.warning(
                    "Runtime 目标不可访问，尝试下一副本。",
                    extra={"event": "runtime.target.unavailable", "role": role, "target": target, "path": path},
                )
                continue
            except httpx.RequestError as exc:
                active_router.mark_failure(role, target)
                last_error = AppException(
                    status_code=502,
                    code=unavailable_error_code or default_error_code,
                    detail="Runtime 服务不可访问。",
                    data={"dispatch_may_have_started": True},
                )
                # ReadError/WriteError/RemoteProtocolError 等可能发生在对端已接收并开始
                # 执行之后。构建 POST 非幂等：禁止换副本重发，交由租约/重试预算收敛（M4）。
                if role == "build" and method.upper() == "POST":
                    logger.error(
                        "Runtime 构建 POST 网络错误且请求可能已到达对端，不换副本重发非幂等请求。",
                        extra={
                            "event": "runtime.build.request_error_no_retry",
                            "role": role,
                            "target": target,
                            "path": path,
                            "error_type": type(exc).__name__,
                        },
                    )
                    raise last_error
                logger.warning(
                    "Runtime 目标不可访问，尝试下一副本。",
                    extra={"event": "runtime.target.unavailable", "role": role, "target": target, "path": path},
                )
                continue

            if response.status_code in _OVERLOAD_STATUS_CODES:
                # 配置/鉴权类 503：所有副本共享配置，换副本只会重复同一故障。
                # 必须保留真实错误码直接失败，不得映射为 RUNTIME_CAPACITY_EXCEEDED。
                if _is_config_or_auth_error(response):
                    error = _build_http_exception(response, default_code=default_error_code)
                    logger.error(
                        "Runtime 目标返回配置/鉴权错误，不换副本直接失败。",
                        extra={
                            "event": "runtime.target.config_error",
                            "role": role,
                            "target": target,
                            "path": path,
                            "status_code": response.status_code,
                            "error_code": error.code,
                        },
                    )
                    raise error
                if role == "build" and method.upper() == "POST":
                    response_code = _extract_response_error_code(response)
                    if response_code not in _BUILD_PRE_DISPATCH_CAPACITY_CODES:
                        active_router.mark_failure(role, target)
                        error = _build_http_exception(
                            response,
                            default_code=default_error_code,
                            extra_data={"dispatch_may_have_started": True},
                        )
                        logger.error(
                            "Runtime 构建 POST 返回非执行前容量错误，不换副本重发。",
                            extra={
                                "event": "runtime.build.ambiguous_capacity_no_retry",
                                "role": role,
                                "target": target,
                                "path": path,
                                "status_code": response.status_code,
                                "error_code": error.code,
                            },
                        )
                        raise error
                overload_seen = True
                active_router.mark_failure(role, target, overloaded=True)
                last_error = _build_http_exception(response, default_code=default_error_code)
                logger.warning(
                    "Runtime 目标满载，尝试下一副本。",
                    extra={
                        "event": "runtime.target.overloaded",
                        "role": role,
                        "target": target,
                        "path": path,
                        "status_code": response.status_code,
                    },
                )
                continue

            if response.status_code >= 500:
                active_router.mark_failure(role, target)
                last_error = _build_http_exception(
                    response,
                    default_code=default_error_code,
                    force_status_code=502,
                    extra_data={"dispatch_may_have_started": True},
                )
                # 构建 POST 非幂等：5xx 可能发生在对端已接收并执行之后，禁止换副本重发。
                if role == "build" and method.upper() == "POST":
                    logger.error(
                        "Runtime 构建 POST 返回服务端错误，不换副本重发非幂等请求。",
                        extra={
                            "event": "runtime.build.http_error_no_retry",
                            "role": role,
                            "target": target,
                            "path": path,
                            "status_code": response.status_code,
                        },
                    )
                    raise last_error
                logger.error(
                    "Runtime 目标返回服务端错误，尝试下一副本。",
                    extra={
                        "event": "runtime.target.failed",
                        "role": role,
                        "target": target,
                        "path": path,
                        "status_code": response.status_code,
                    },
                )
                continue

            if response.status_code >= 400:
                # 业务错误对所有副本等价，直接返回，不消耗其它副本容量。
                logger.warning(
                    "Runtime 请求返回业务错误。",
                    extra={
                        "event": "runtime.request.rejected",
                        "role": role,
                        "target": target,
                        "path": path,
                        "status_code": response.status_code,
                    },
                )
                raise _build_http_exception(response, default_code=default_error_code)

            try:
                payload = response.json()
            except ValueError:
                active_router.mark_failure(role, target)
                last_error = AppException(
                    status_code=502,
                    code=invalid_response_code or default_error_code,
                    detail="Runtime 返回了非法 JSON。",
                    data={"dispatch_may_have_started": True},
                )
                # 非法 JSON 意味着对端已给出响应（可能已执行），构建 POST 不得换副本。
                if role == "build" and method.upper() == "POST":
                    logger.error(
                        "Runtime 构建 POST 返回非法 JSON，不换副本重发非幂等请求。",
                        extra={
                            "event": "runtime.build.invalid_response_no_retry",
                            "role": role,
                            "target": target,
                            "path": path,
                        },
                    )
                    raise last_error
                logger.warning(
                    "Runtime 目标返回非法 JSON，尝试下一副本。",
                    extra={"event": "runtime.target.invalid_response", "role": role, "target": target, "path": path},
                )
                continue
            if not isinstance(payload, dict):
                active_router.mark_failure(role, target)
                last_error = AppException(
                    status_code=502,
                    code=invalid_response_code or default_error_code,
                    detail="Runtime 响应必须是 JSON 对象。",
                    data={"dispatch_may_have_started": True},
                )
                if role == "build" and method.upper() == "POST":
                    logger.error(
                        "Runtime 构建 POST 响应结构非法，不换副本重发非幂等请求。",
                        extra={
                            "event": "runtime.build.invalid_response_no_retry",
                            "role": role,
                            "target": target,
                            "path": path,
                        },
                    )
                    raise last_error
                continue

            active_router.mark_success(role, target)
            return dict(payload)

    # 所有副本均未成功：满载映射为稳定容量错误，其余保留最后一次失败语义。
    if overload_seen:
        raise AppException(
            status_code=503,
            code=RUNTIME_CAPACITY_EXCEEDED,
            detail="Runtime 计算副本已满载，请稍后重试。",
            data={"role": role, "targets": targets},
            headers={"Retry-After": RETRY_AFTER_SECONDS},
        )
    if last_error is not None:
        raise last_error
    raise AppException(
        status_code=502,
        code=unavailable_error_code or default_error_code,
        detail="Runtime 请求失败。",
    )

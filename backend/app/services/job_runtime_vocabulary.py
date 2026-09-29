"""文件功能：定义持久化任务列词汇，把契约标准名映射到各队列历史列名。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class JobColumnVocabulary:
    """持久化任务列词汇：契约标准名 → 模型属性名。

    新任务类型只注册本结构（或复用预置词汇）与领域取值，不再手写 claim 时序。
    可选列用 `None` 表示该模型没有这一列；有列但历史命名不同时填属性名。
    """

    # 状态机列
    status: str = "status"
    # Worker / Lease
    owner: str = "worker_id"
    lease_expires_at: str = "lease_expires_at"
    heartbeat: str = "heartbeat_at"
    # 可选围栏代次：认领/恢复时 +1，用于阻断过期 Worker 写回
    lease_generation: str | None = None
    # Attempt
    attempt_count: str = "attempt_count"
    max_attempts: str | None = None
    # 取消
    cancel_requested_at: str = "cancel_requested_at"
    # 错误（缺列的模型声明为 None，恢复/终态不得写空列名）
    error_code: str | None = "error_code"
    error_message: str | None = "error_message"
    # 时间戳
    started_at: str = "started_at"
    finished_at: str = "finished_at"
    # 可选退避：恢复后下次可领取时刻
    next_attempt_at: str | None = None

    def attribute(self, model: type[Any], name: str) -> Any:
        """按词汇取出模型列对象；列不存在时抛出明确错误，避免静默写空列名。"""

        attr = getattr(model, name, None)
        if attr is None:
            raise AttributeError(f"{model.__name__} 缺少列 {name!r}（JobColumnVocabulary 映射）")
        return attr

    def owner_column(self, model: type[Any]) -> Any:
        """返回拥有者列。"""

        return self.attribute(model, self.owner)

    def heartbeat_column(self, model: type[Any]) -> Any:
        """返回心跳列。"""

        return self.attribute(model, self.heartbeat)

    def cancel_column(self, model: type[Any]) -> Any:
        """返回取消请求列。"""

        return self.attribute(model, self.cancel_requested_at)

    def generation_column(self, model: type[Any]) -> Any | None:
        """返回围栏代次列；未声明时返回空。"""

        if not self.lease_generation:
            return None
        return self.attribute(model, self.lease_generation)

    def optional_attribute(self, model: type[Any], name: str | None) -> Any | None:
        """取出可选列；名称未声明或模型无此列时返回空。"""

        if not name:
            return None
        return getattr(model, name, None)


# 标准词汇：截图 / 回填 / 页面变更 / 组件变更 / ExternalTask / 图片
# （图片终态拼写归一前仍用标准列名，见契约 §3）
STANDARD_JOB_VOCABULARY = JobColumnVocabulary()

# ProjectBuildJob 历史命名：lease_owner / claimed_at；无 error_code 列
PROJECT_BUILD_VOCABULARY = JobColumnVocabulary(
    owner="lease_owner",
    heartbeat="claimed_at",
    error_code=None,
    error_message="error_message",
    max_attempts="max_attempts",
)

# ApiMutationJob：last_error_code + lease_generation 围栏 + next_attempt_at 退避
MUTATION_JOB_VOCABULARY = JobColumnVocabulary(
    error_code="last_error_code",
    error_message="error_json",
    lease_generation="lease_generation",
    max_attempts="max_attempts",
    next_attempt_at="next_attempt_at",
)

# RenderRequest：claim_generation 围栏；退避列名为 retry_after
RENDER_REQUEST_VOCABULARY = JobColumnVocabulary(
    lease_generation="claim_generation",
    max_attempts="max_attempts",
    next_attempt_at="retry_after",
)

"""文件功能：验证进程内运行态后端的命令语义、并发可见性、TTL 与 payload 预算。"""

from __future__ import annotations

import threading

import pytest

from app.services.runtime_state import (
    InMemoryRuntimeStateBackend,
    RuntimeStateCapacityError,
    RuntimeStateTypeError,
)


class _Clock:
    """可控时钟，避免 TTL 断言依赖真实时间。"""

    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_missing_key_should_follow_redis_absent_semantics() -> None:
    """缺失 key 的读写必须返回 Redis 兼容结果，而不是抛错或造出空值。"""

    backend = InMemoryRuntimeStateBackend(instance_name="test")

    assert backend.get("absent") is None
    assert backend.ttl("absent") == -2
    assert backend.delete("absent") == 0
    assert backend.expire("absent", 60) is False
    assert backend.hget("absent_hash", "field") is None
    assert backend.hmget("absent_hash", ["a", "b"]) == [None, None]
    assert backend.hgetall("absent_hash") == {}
    assert backend.incr("absent_counter") == 1


def test_set_nx_should_reject_duplicate_claim_without_overwriting() -> None:
    """重复 SET NX 必须失败且保留首次写入值，供短锁与节流复用。"""

    backend = InMemoryRuntimeStateBackend(instance_name="test")

    assert backend.set("lock", "first", ex=60, nx=True) is True
    assert backend.set("lock", "second", ex=60, nx=True) is False
    assert backend.get("lock") == "first"


def test_incr_should_keep_ttl_and_reject_non_integer_values() -> None:
    """INCR 只在首次写入后设置 TTL，非整数值按 Redis 语义报错。"""

    clock = _Clock()
    backend = InMemoryRuntimeStateBackend(instance_name="test", clock=clock)

    assert backend.incr("counter") == 1
    backend.expire("counter", 60)
    clock.now += 10
    assert backend.incr("counter") == 2
    assert backend.ttl("counter") == 50

    backend.set("text", "abc")
    with pytest.raises(ValueError, match="不是整数"):
        backend.incr("text")


def test_empty_hset_should_not_create_key() -> None:
    """空 HSET 与 Redis 一致：返回 0 且不创建 key。"""

    backend = InMemoryRuntimeStateBackend(instance_name="test")

    assert backend.hset("absent_hash", {}) == 0
    assert backend.hgetall("absent_hash") == {}
    assert backend.stats().active_keys == 0
    assert "absent_hash" not in backend._state.hashes


def test_expire_should_delete_key_on_non_positive_ttl() -> None:
    """TTL 设为非正数按 Redis 语义立即删除 key。"""

    backend = InMemoryRuntimeStateBackend(instance_name="test")
    backend.set("k", "v", ex=60)

    assert backend.expire("k", 0) is True
    assert backend.get("k") is None
    assert backend.ttl("k") == -2


def test_hash_commands_should_report_added_fields_and_preserve_order() -> None:
    """HSET 只统计新增字段，HMGET 保持输入顺序并保留缺失占位。"""

    backend = InMemoryRuntimeStateBackend(instance_name="test")

    assert backend.hset("modules", {"a": "1", "b": "2"}) == 2
    assert backend.hset("modules", {"a": "3", "c": "4"}) == 1
    assert backend.hget("modules", "a") == "3"
    assert backend.hmget("modules", ["c", "missing", "a"]) == ["4", None, "3"]
    assert backend.hgetall("modules") == {"a": "3", "b": "2", "c": "4"}


def test_delete_should_count_across_string_and_hash_keys() -> None:
    """DELETE 计数必须跨类型统计，并忽略不存在与重复的 key。"""

    backend = InMemoryRuntimeStateBackend(instance_name="test")
    backend.set("s", "v")
    backend.hset("h", {"f": "v"})

    assert backend.delete("s", "h", "missing", "s") == 2
    assert backend.stats().active_keys == 0


def test_type_conflicts_should_be_rejected_like_redis_wrongtype() -> None:
    """String 与 Hash 混用必须失败，避免业务静默读到错误结构。"""

    backend = InMemoryRuntimeStateBackend(instance_name="test")
    backend.set("s", "v")
    backend.hset("h", {"f": "v"})

    with pytest.raises(RuntimeStateTypeError):
        backend.get("h")
    with pytest.raises(RuntimeStateTypeError):
        backend.incr("h")
    with pytest.raises(RuntimeStateTypeError):
        backend.hget("s", "f")
    with pytest.raises(RuntimeStateTypeError):
        backend.hset("s", {"f": "v"})


def test_expired_key_should_be_reusable_without_stale_ttl() -> None:
    """过期后重新写入不得继承旧 TTL，避免新数据被误删。"""

    clock = _Clock()
    backend = InMemoryRuntimeStateBackend(instance_name="test", clock=clock)
    backend.set("k", "old", ex=1)

    clock.now += 5
    assert backend.set("k", "new") is True
    assert backend.get("k") == "new"
    assert backend.ttl("k") == -1


def test_concurrent_set_nx_should_allow_exactly_one_winner() -> None:
    """并发 SET NX 只能有一个赢家，领取与节流语义不能被并发击穿。"""

    backend = InMemoryRuntimeStateBackend(instance_name="test")
    barrier = threading.Barrier(8)
    results: list[bool] = []

    def worker() -> None:
        barrier.wait(timeout=5)
        results.append(backend.set("lock", "owner", ex=60, nx=True))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert len(results) == 8
    assert results.count(True) == 1


def test_batch_should_not_expose_partial_state_to_other_threads() -> None:
    """artifact 批次必须对其它线程原子可见，读者不能看到半个批次。"""

    class _BlockingBackend(InMemoryRuntimeStateBackend):
        """在批处理中途插入确定调度点，验证整批加锁范围。"""

        def __init__(self) -> None:
            super().__init__(instance_name="test")
            self.entered = threading.Event()
            self.release = threading.Event()

        def expire(self, key: str, seconds: int) -> bool:
            self.entered.set()
            self.release.wait(timeout=5)
            return super().expire(key, seconds)

    backend = _BlockingBackend()
    batch = backend.batch()
    batch.set("artifact:manifest", "manifest", ex=60)
    batch.hset("artifact:modules", {"entry": "code"})
    batch.expire("artifact:modules", 60)

    executor = threading.Thread(target=batch.execute)
    executor.start()
    assert backend.entered.wait(timeout=5)

    observed: list[str | None] = []
    reader = threading.Thread(target=lambda: observed.append(backend.get("artifact:manifest")))
    reader.start()
    reader.join(timeout=0.2)

    assert backend.release.set() is None
    executor.join(timeout=5)
    reader.join(timeout=5)

    assert observed == ["manifest"]
    assert backend.hget("artifact:modules", "entry") == "code"


def test_batch_should_roll_back_entirely_when_budget_is_exceeded() -> None:
    """批处理超预算时必须整批回滚，不能留下半个 artifact。"""

    backend = InMemoryRuntimeStateBackend(instance_name="test", max_bytes=200, max_item_bytes=10_000)
    batch = backend.batch()
    batch.set("artifact:a", "x" * 50, ex=60)
    batch.set("artifact:b", "y" * 500, ex=60)

    with pytest.raises(RuntimeStateCapacityError):
        batch.execute()

    assert backend.get("artifact:a") is None
    assert backend.get("artifact:b") is None
    assert backend.stats().active_keys == 0
    assert backend.stats().approx_bytes == 0
    assert backend.stats().capacity_rejections == 1


def test_batch_should_roll_back_when_single_item_exceeds_limit() -> None:
    """批处理中单项超限时同样整批回滚并保留原值。"""

    backend = InMemoryRuntimeStateBackend(instance_name="test", max_item_bytes=64)
    backend.hset("artifact:modules", {"a": "1"})
    batch = backend.batch()
    batch.hset("artifact:modules", {"a": "2", "b": "z" * 200})
    batch.expire("artifact:modules", 60)

    with pytest.raises(RuntimeStateCapacityError):
        batch.execute()

    assert backend.hget("artifact:modules", "a") == "1"
    assert backend.hget("artifact:modules", "b") is None
    assert backend.ttl("artifact:modules") == -1


def test_batch_should_roll_back_on_non_capacity_errors() -> None:
    """批处理中途类型冲突同样必须整批回滚，不能留下半批写入。"""

    backend = InMemoryRuntimeStateBackend(instance_name="test")
    backend.set("s", "v")

    batch = backend.batch()
    batch.set("s2", "new")
    batch.hset("s", {"f": "v"})
    with pytest.raises(RuntimeStateTypeError):
        batch.execute()

    assert backend.get("s2") is None
    assert backend.get("s") == "v"
    with pytest.raises(RuntimeStateTypeError):
        backend.hget("s", "f")


def test_total_budget_should_cover_overwrite_hash_delete_and_expiry() -> None:
    """预算统计必须覆盖覆盖写、Hash 增减、删除与过期回收。"""

    clock = _Clock()
    backend = InMemoryRuntimeStateBackend(instance_name="test", max_bytes=400, max_item_bytes=10_000, clock=clock)
    backend.set("k", "a" * 100)
    assert backend.stats().approx_bytes == 101

    backend.set("k", "b" * 200)
    assert backend.stats().approx_bytes == 201

    backend.hset("h", {"f": "c" * 100})
    assert backend.stats().approx_bytes == 201 + 1 + 1 + 100

    backend.hset("h", {"f": "d"})
    assert backend.stats().approx_bytes == 201 + 1 + 1 + 1

    assert backend.delete("h") == 1
    assert backend.stats().approx_bytes == 201

    backend.expire("k", 1)
    clock.now += 5
    assert backend.purge_expired() == 1
    assert backend.stats().approx_bytes == 0
    assert backend.stats().active_keys == 0


def test_total_budget_should_reject_write_before_it_takes_effect() -> None:
    """超预算写入必须在生效前拒绝，并登记容量拒绝次数。"""

    backend = InMemoryRuntimeStateBackend(instance_name="test", max_bytes=200, max_item_bytes=10_000)
    backend.set("k", "x" * 150)

    with pytest.raises(RuntimeStateCapacityError):
        backend.set("k2", "y" * 150)

    assert backend.get("k2") is None
    assert backend.stats().active_keys == 1
    assert backend.stats().capacity_rejections == 1


def test_sweep_should_release_expired_keys_without_later_access() -> None:
    """未再次访问的过期 key 也必须被清扫释放，并记录清扫统计。"""

    clock = _Clock()
    backend = InMemoryRuntimeStateBackend(instance_name="test", clock=clock)
    backend.set("a", "1", ex=10)
    backend.hset("b", {"f": "2"})
    backend.expire("b", 10)
    backend.set("c", "3")

    clock.now += 60
    assert backend.purge_expired() == 2

    stats = backend.stats()
    assert stats.active_keys == 1
    assert stats.sweep_count == 1
    assert stats.last_sweep_at is not None
    assert stats.last_sweep_seconds is not None

    backend.record_sweep_failure()
    assert backend.stats().sweep_failures == 1
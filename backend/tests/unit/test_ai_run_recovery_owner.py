"""文件功能：验证智能体 Run 启动恢复的 owner 过滤语义，防止多副本误杀活跃 Run。"""

from __future__ import annotations

import os
from datetime import timedelta

from app.ai.run_recovery import (
    parse_process_owner,
    process_is_alive,
    should_recover_run,
)
from app.core.time_utils import utc_now


def test_parse_process_owner_should_split_hostname_pid_uuid() -> None:
    """标准 hostname:pid:uuid 形态应解析出主机与 pid。"""

    parsed = parse_process_owner("host-a:12345:abcdef0123")
    assert parsed == ("host-a", 12345)


def test_parse_process_owner_should_tolerate_colon_in_hostname() -> None:
    """主机名含冒号时从右侧拆分，不得把 uuid 误当成 pid。"""

    parsed = parse_process_owner("weird:host:99:deadbeef")
    assert parsed == ("weird:host", 99)


def test_parse_process_owner_should_reject_invalid_shapes() -> None:
    """空串、缺段、非法 pid 一律返回 None，由调用方按无主处理。"""

    assert parse_process_owner(None) is None
    assert parse_process_owner("") is None
    assert parse_process_owner("only-host") is None
    assert parse_process_owner("host:not-int:uuid") is None
    assert parse_process_owner("host:0:uuid") is None


def test_process_is_alive_should_return_true_for_current_pid() -> None:
    """当前进程自身必须视为存活，避免启动时误收自己的活跃 Run。"""

    assert process_is_alive(os.getpid()) is True


def test_should_recover_run_should_skip_foreign_host_even_if_unowned_policy() -> None:
    """其它主机归属的 Run 在任何策略下都不得被本副本收敛。"""

    assert should_recover_run(
        process_owner="other-host:1:abc",
        local_hostname="local-host",
        current_pid=100,
        include_unowned=True,
    ) is False


def test_should_recover_run_should_skip_live_sibling_on_same_host() -> None:
    """同机仍存活的 sibling worker Run 不得被收敛。"""

    assert should_recover_run(
        process_owner=f"local-host:{os.getpid()}:abc",
        local_hostname="local-host",
        current_pid=os.getpid(),
        include_unowned=True,
    ) is False


def test_should_recover_run_should_recover_dead_process_on_same_host() -> None:
    """本机已死进程（极大 pid，不可能存活）应被收敛。"""

    dead_pid = 2**22 + 12345
    assert should_recover_run(
        process_owner=f"local-host:{dead_pid}:abc",
        local_hostname="local-host",
        current_pid=1,
        include_unowned=False,
    ) is True


def test_should_recover_run_should_gate_unowned_by_flag() -> None:
    """无主遗留仅在 include_unowned 时收敛；多副本默认拒绝。"""

    assert should_recover_run(
        process_owner=None,
        local_hostname="local-host",
        current_pid=1,
        include_unowned=True,
    ) is True
    assert should_recover_run(
        process_owner=None,
        local_hostname="local-host",
        current_pid=1,
        include_unowned=False,
    ) is False
    assert should_recover_run(
        process_owner="broken-owner",
        local_hostname="local-host",
        current_pid=1,
        include_unowned=False,
    ) is False


def test_utc_now_anchor_is_timezone_aware() -> None:
    """时间锚点保持 aware UTC，避免恢复判断混用 naive/aware。"""

    now = utc_now()
    assert now.tzinfo is not None
    assert (utc_now() - now) >= timedelta(0)

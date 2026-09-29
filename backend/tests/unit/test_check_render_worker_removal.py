"""文件功能：验证 Renderer Worker 摘除门禁 CLI 的摘要与参数边界。"""

from __future__ import annotations

import pytest

from app.scripts.check_render_worker_removal import _attempt_payload, _print_summary, main


def test_attempt_payload_should_expose_identity_fields() -> None:
    """未释放 attempt 摘要应包含 id/request/epoch/status，便于运维定位。"""

    class FakeAttempt:
        id = 7
        attempt_uid = "uid-7"
        request_id = 3
        worker_id = "renderer-1"
        worker_epoch = "epoch-a"
        status = "running"
        lease_expires_at = None

    payload = _attempt_payload(FakeAttempt())
    assert payload["id"] == 7
    assert payload["attempt_uid"] == "uid-7"
    assert payload["status"] == "running"


def test_main_should_require_worker_id() -> None:
    """缺少 --worker-id 时 CLI 应直接报参数错误。"""

    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code == 2


def test_print_summary_safe_and_unsafe(capsys: pytest.CaptureFixture[str]) -> None:
    """摘要输出应区分可摘除与不可摘除两种门禁结果。"""

    _print_summary({
        "worker_id": "renderer-1",
        "safe_to_remove": True,
        "unreleased_attempt_count": 0,
        "unreleased_attempts": [],
    })
    assert "可安全摘除" in capsys.readouterr().out

    _print_summary({
        "worker_id": "renderer-1",
        "safe_to_remove": False,
        "unreleased_attempt_count": 1,
        "unreleased_attempts": [{
            "id": 1,
            "attempt_uid": "u1",
            "request_id": 2,
            "worker_id": "renderer-1",
            "worker_epoch": "e1",
            "status": "running",
            "lease_expires_at": None,
        }],
    })
    out = capsys.readouterr().out
    assert "不可摘除" in out
    assert "attempt#1" in out

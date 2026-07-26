"""文件功能：验证图片生成队列按同轮调用聚合终态结果后再恢复智能体运行。"""

from types import SimpleNamespace

from app.ai.image_generation_queue import (
    _build_image_deferred_results,
    _image_deferred_call_ids,
)


def test_image_requirement_should_collect_all_generation_call_ids() -> None:
    """同一轮包含多张图片时，应保留全部 deferred tool call ID 及顺序。"""

    payload = {
        "tool_execution": {
            "tool_calls": [
                {
                    "tool_call_id": "call-image-1",
                    "tool_name": "generate_image",
                    "metadata": {"kind": "image_generation", "job_id": "job-1"},
                },
                {
                    "tool_call_id": "call-image-2",
                    "tool_name": "generate_image",
                    "metadata": {"kind": "image_generation", "job_id": "job-2"},
                },
            ]
        }
    }

    assert _image_deferred_call_ids(payload, fallback_call_id="fallback") == [
        "call-image-1",
        "call-image-2",
    ]


def test_image_batch_should_wait_for_every_job_and_return_every_result() -> None:
    """任一任务未终态时不得续跑；全部结束后应一次回灌成功与失败结果。"""

    completed_job = SimpleNamespace(
        deferred_tool_call_id="call-image-1",
        status="completed",
        result_json={"status": "completed", "assets": [{"id": 1}]},
        error_code=None,
        error_message=None,
    )
    running_job = SimpleNamespace(
        deferred_tool_call_id="call-image-2",
        status="waiting_provider",
        result_json=None,
        error_code=None,
        error_message=None,
    )

    assert (
        _build_image_deferred_results(
            ["call-image-1", "call-image-2"],
            [completed_job, running_job],  # type: ignore[list-item]
        )
        is None
    )

    running_job.status = "error"
    running_job.error_code = "AI_IMAGE_PROVIDER_FAILED"
    running_job.error_message = "第二张图片生成失败。"
    deferred = _build_image_deferred_results(
        ["call-image-1", "call-image-2"],
        [completed_job, running_job],  # type: ignore[list-item]
    )

    assert deferred is not None
    assert set(deferred.calls) == {"call-image-1", "call-image-2"}
    assert deferred.calls["call-image-1"] == completed_job.result_json
    assert deferred.calls["call-image-2"]["error"]["code"] == "AI_IMAGE_PROVIDER_FAILED"

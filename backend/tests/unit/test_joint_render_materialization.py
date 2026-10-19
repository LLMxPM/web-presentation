"""文件功能：验证布局完成后图片下载失败隔离、旧 Worker 降级与身份防线。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.services.rendering.result_materializer import materialize_result
from render_contracts.errors import RenderExecutionError


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["download_failure", "old_worker", "identity_mismatch"])
async def test_joint_materialization_failure_boundary(mode):
    """旧 Worker 不得误报有图，产物故障保留布局，身份不可信使整次请求失败。"""
    payload = {"request_id": "1", "attempt_id": "a", "request_digest": "d", "input_digest": "i",
               "render_profile_digest": "p", "layout": {"nodes": 1},
               "screenshot": {"status": "available", "reason_code": None, "retryable": False},
               "artifacts": [{"name": "page.png", "byte_length": 20, "sha256": "h", "content_type": "image/png"}]}
    if mode == "old_worker":
        payload.pop("screenshot")
    if mode == "identity_mismatch":
        payload["attempt_id"] = "late-attempt"
    request = SimpleNamespace(id=1, workspace_id=2, operation="page.diagnose", operation_options={"capture_screenshot": True},
                              request_digest="d", input_digest="i", render_profile_digest="p")
    kwargs = dict(client=SimpleNamespace(fetch_artifact=AsyncMock(side_effect=RuntimeError("download failed"))),
                  settings=SimpleNamespace(render_artifact_max_bytes=1024), endpoint=None, request=request,
                  attempt=SimpleNamespace(id=3, attempt_uid="a"), receipt=SimpleNamespace(result_descriptor={"result": payload}))
    if mode == "identity_mismatch":
        with pytest.raises(RenderExecutionError):
            await materialize_result(**kwargs)
    else:
        result = await materialize_result(**kwargs)
        assert result["payload"]["layout"] == {"nodes": 1}
        assert result["payload"]["screenshot"]["status"] == ("skipped" if mode == "old_worker" else "failed")
        assert result["object_refs"] == {}

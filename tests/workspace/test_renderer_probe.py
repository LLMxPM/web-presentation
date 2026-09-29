"""文件功能：验证镜像探针通过正式请求契约取回并核对产物，不启动服务或浏览器。"""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from render_contracts.schema import ExecutionRequest
from render_contracts.tokens import verify_worker_credential

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "renderer_probe", ROOT / "scripts/contracts/renderer-image-probe.py"
)
assert SPEC and SPEC.loader
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


@pytest.mark.parametrize(
    "status,wrong_hash", [("succeeded", False), ("failed", False), ("succeeded", True)]
)
def test_probe_uses_control_api_and_rejects_failed_execution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, status: str, wrong_hash: bool
) -> None:
    """正式 DTO、服务身份、终态与 SHA 均参与检查；失败不能留下成功证据。"""
    secret = b"only-unit-test-secret"
    calls = []
    closed = []
    monkeypatch.setattr(
        PROBE,
        "get_renderer_settings",
        lambda: SimpleNamespace(
            render_worker_id="renderer-local",
            credential_secret=secret,
            render_port=7400,
        ),
    )
    monkeypatch.setattr(
        PROBE,
        "ThreadingHTTPServer",
        lambda *_args: SimpleNamespace(
            server_port=7374,
            serve_forever=lambda: None,
            shutdown=lambda: closed.append(True),
            server_close=lambda: None,
        ),
    )
    content = b"png-byte-download"
    capabilities = {
        "slot_state": "idle",
        "render_profile_digest": "profile.v1",
        "worker_id": "renderer-local",
        "worker_epoch": "actual-server-epoch",
        "slot_generation": 5,
    }

    def respond(request, **_kwargs):
        """替代传输层，校验发出的真实 DTO；控制层之外不替换生产 Renderer 实现。"""
        assert (
            verify_worker_credential(
                request.get_header("X-render-service-token"), secret
            )
            == "backend:renderer-local"
        )
        calls.append((request.method, request.full_url))
        if request.full_url.endswith("/capabilities"):
            value = capabilities
        elif request.method == "POST":
            dto = ExecutionRequest.from_dict(json.loads(request.data))
            dto.validate()
            assert dto.admission_ticket.worker_epoch == "actual-server-epoch"
            assert dto.admission_ticket.slot_generation == 6
            assert (
                dto.preview_access.navigation_base_url
                == "http://127.0.0.1:7374/preview"
            )
            value = {"status": "accepted"}
        elif request.full_url.endswith("/artifacts/page.png"):
            return io.BytesIO(content)
        elif request.method == "PUT":
            value = {"consumed": True}
        else:
            value = {
                "status": status,
                "cleaned_at": "2026-09-30T00:00:00Z",
                "error": None,
                "result_descriptor": {
                    "artifacts": [
                        {
                            "byte_length": len(content),
                            "sha256": "bad"
                            if wrong_hash
                            else hashlib.sha256(content).hexdigest(),
                        }
                    ]
                },
            }
        return io.BytesIO(json.dumps(value).encode())

    monkeypatch.setattr(PROBE, "urlopen", respond)
    if status == "failed" or wrong_hash:
        with pytest.raises(RuntimeError):
            PROBE.run_probe(tmp_path / "evidence")
        assert not (tmp_path / "evidence/receipt.json").exists()
    else:
        PROBE.run_probe(tmp_path / "evidence")
        assert (tmp_path / "evidence/page.png").read_bytes() == content
        assert any(
            method == "PUT" and path.endswith("/result-consumption")
            for method, path in calls
        )
    assert closed == [True]

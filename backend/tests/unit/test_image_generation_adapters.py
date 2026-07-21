"""文件功能：验证独立生图供应商请求映射、同步异步协议与能力边界。"""

import base64
from types import SimpleNamespace

import httpx
import pytest

from app.core.exceptions import AppException
from app.services.dashscope_image_generation_adapter import DashScopeImageGenerationAdapter
from app.services.image_generation.contracts import ImageGenerationInput, ProviderTaskCursor
from app.services.image_generation.registry import get_image_model_spec
from app.services.image_generation_adapters import OpenAiImageGenerationAdapter


def _config(model_id: str = "wan2.7-image-pro") -> SimpleNamespace:
    """构造不包含真实密钥的百炼模型配置。"""

    return SimpleNamespace(
        model_id=model_id,
        provider_config=SimpleNamespace(
            api_key_ciphertext="encrypted",
            base_url="https://workspace.cn-beijing.maas.aliyuncs.com/api/v1",
        ),
    )


def _request(**overrides) -> ImageGenerationInput:
    """构造默认文生图请求。"""

    values = {
        "operation": "generate",
        "prompt": "蓝色几何海报",
        "aspect_ratio": "3:2",
        "resolution_tier": "high",
        "quality": "auto",
        "count": 1,
        "references": [],
        "mask": None,
    }
    values.update(overrides)
    return ImageGenerationInput(**values)


def _model():
    """读取百炼默认模型的注册能力。"""

    return get_image_model_spec("dashscope_image", "wan2.7-image-pro")


@pytest.mark.asyncio
async def test_dashscope_submit_should_return_persistable_task(monkeypatch) -> None:
    """百炼提交只返回 task 元数据，不泄露输入图片或临时结果。"""

    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs):  # noqa: ANN003
            _ = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):  # noqa: ANN001
            return False

        async def post(self, url, *, headers, json):  # noqa: ANN001
            captured.update(url=url, headers=headers, json=json)
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={"request_id": "request-1", "output": {"task_id": "task-1", "task_status": "PENDING"}},
            )

    monkeypatch.setattr("app.services.dashscope_image_generation_adapter.httpx.AsyncClient", FakeClient)
    adapter = DashScopeImageGenerationAdapter()
    monkeypatch.setattr(adapter._cipher, "decrypt", lambda _value: "sk-test")

    result = await adapter.submit(_config(), _model(), _request())

    assert result.status == "waiting"
    assert result.provider_task_id == "task-1"
    assert result.provider_request_id == "request-1"
    assert str(captured["url"]).endswith("/services/aigc/image-generation/generation")
    assert captured["json"]["parameters"]["size"] == "2496*1664"  # type: ignore[index]


@pytest.mark.asyncio
async def test_dashscope_poll_should_download_success_images(monkeypatch) -> None:
    """百炼成功轮询应立即下载 HTTPS 图片并只返回字节。"""

    class FakeClient:
        def __init__(self, **kwargs):  # noqa: ANN003
            _ = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):  # noqa: ANN001
            return False

        async def get(self, url, *, headers=None):  # noqa: ANN001
            if "/tasks/" in url:
                return httpx.Response(
                    200,
                    request=httpx.Request("GET", url),
                    json={
                        "request_id": "request-2",
                        "output": {
                            "task_status": "SUCCEEDED",
                            "choices": [{"message": {"content": [{"type": "image", "image": "https://result.test/a.png"}]}}],
                        },
                    },
                )
            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                headers={"content-type": "image/png"},
                content=b"png-bytes",
            )

    monkeypatch.setattr("app.services.dashscope_image_generation_adapter.httpx.AsyncClient", FakeClient)
    adapter = DashScopeImageGenerationAdapter()
    monkeypatch.setattr(adapter._cipher, "decrypt", lambda _value: "sk-test")

    result = await adapter.resume(
        _config(),
        _model(),
        ProviderTaskCursor(task_id="task-1", status="PENDING", cancellable=True),
    )

    assert result.status == "completed"
    assert result.provider_status == "SUCCEEDED"
    assert result.images[0].content == b"png-bytes"


@pytest.mark.asyncio
async def test_dashscope_submission_timeout_should_be_terminal_unknown(monkeypatch) -> None:
    """提交超时无法确认是否计费时应返回不可自动重试的稳定错误。"""

    class TimeoutClient:
        def __init__(self, **kwargs):  # noqa: ANN003
            _ = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):  # noqa: ANN001
            return False

        async def post(self, url, *, headers, json):  # noqa: ANN001
            _ = (headers, json)
            raise httpx.ReadTimeout("unknown", request=httpx.Request("POST", url))

    monkeypatch.setattr("app.services.dashscope_image_generation_adapter.httpx.AsyncClient", TimeoutClient)
    adapter = DashScopeImageGenerationAdapter()
    monkeypatch.setattr(adapter._cipher, "decrypt", lambda _value: "sk-test")

    with pytest.raises(AppException) as exc_info:
        await adapter.submit(_config(), _model(), _request())
    assert exc_info.value.code == "AI_IMAGE_PROVIDER_SUBMISSION_UNKNOWN"
    assert not (exc_info.value.data or {}).get("retryable")


@pytest.mark.asyncio
async def test_dashscope_rate_limit_should_be_retryable(monkeypatch) -> None:
    """明确未创建任务的限流响应应允许队列按租约重试。"""

    class RateLimitedClient:
        def __init__(self, **kwargs):  # noqa: ANN003
            _ = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):  # noqa: ANN001
            return False

        async def post(self, url, *, headers, json):  # noqa: ANN001
            _ = (headers, json)
            return httpx.Response(
                429,
                request=httpx.Request("POST", url),
                json={"code": "Throttling", "message": "rate limited"},
            )

    monkeypatch.setattr("app.services.dashscope_image_generation_adapter.httpx.AsyncClient", RateLimitedClient)
    adapter = DashScopeImageGenerationAdapter()
    monkeypatch.setattr(adapter._cipher, "decrypt", lambda _value: "sk-test")

    with pytest.raises(AppException) as exc_info:
        await adapter.submit(_config(), _model(), _request())
    assert exc_info.value.code == "AI_IMAGE_PROVIDER_THROTTLING"
    assert exc_info.value.data == {"retryable": True}


def test_dashscope_should_reject_mask_and_non_auto_quality() -> None:
    """百炼首版应在入队前拒绝未声明能力。"""

    adapter = DashScopeImageGenerationAdapter()
    with pytest.raises(AppException, match="蒙版"):
        adapter.validate(_config(), _model(), _request(operation="edit", references=[("a.png", "image/png", b"a")], mask=("m.png", "image/png", b"m")))
    with pytest.raises(AppException) as exc_info:
        adapter.validate(_config(), _model(), _request(quality="high"))
    assert exc_info.value.code == "AI_IMAGE_QUALITY_UNSUPPORTED"
    assert exc_info.value.data == {
        "field": "quality",
        "received": "high",
        "allowed_values": ["auto"],
        "model_id": "wan2.7-image-pro",
        "retry_patch": {"quality": "auto"},
    }


@pytest.mark.asyncio
async def test_dashscope_sync_mode_should_return_images_without_task(monkeypatch) -> None:
    """同步模式应调用 multimodal-generation，并直接下载响应图片。"""

    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs):  # noqa: ANN003
            _ = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):  # noqa: ANN001
            return False

        async def post(self, url, *, headers, json):  # noqa: ANN001
            captured.update(url=url, headers=headers, json=json)
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={"output": {"choices": [{"message": {"content": [{"type": "image", "image": "https://result.test/a.png"}]}}]}},
            )

        async def get(self, url, *, headers=None):  # noqa: ANN001
            _ = headers
            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                headers={"content-type": "image/png"},
                content=b"png-bytes",
            )

    monkeypatch.setattr("app.services.dashscope_image_generation_adapter.httpx.AsyncClient", FakeClient)
    adapter = DashScopeImageGenerationAdapter()
    monkeypatch.setattr(adapter._cipher, "decrypt", lambda _value: "sk-test")
    request = _request(advanced_options={"execution_mode": "sync", "watermark": True})

    result = await adapter.submit(_config(), _model(), request)

    assert result.status == "completed"
    assert result.images[0].content == b"png-bytes"
    assert str(captured["url"]).endswith("/services/aigc/multimodal-generation/generation")
    assert "X-DashScope-Async" not in captured["headers"]  # type: ignore[operator]
    assert captured["json"]["parameters"]["watermark"] is True  # type: ignore[index]


@pytest.mark.asyncio
async def test_openai_edit_should_filter_operation_options_and_preserve_output_mime(monkeypatch) -> None:
    """OpenAI 编辑不应收到 generations 专属参数，Base64 输出应沿用配置格式。"""

    captured: dict[str, object] = {}

    class FakeImages:
        async def edit(self, **kwargs):  # noqa: ANN003
            captured.update(kwargs)
            encoded = base64.b64encode(b"jpeg-bytes").decode("ascii")
            return SimpleNamespace(data=[SimpleNamespace(b64_json=encoded)])

    class FakeOpenAI:
        def __init__(self, **kwargs):  # noqa: ANN003
            _ = kwargs
            self.images = FakeImages()

    monkeypatch.setattr("app.services.image_generation_adapters.AsyncOpenAI", FakeOpenAI)
    adapter = OpenAiImageGenerationAdapter()
    monkeypatch.setattr(adapter._cipher, "decrypt", lambda _value: "sk-test")
    config = SimpleNamespace(
        model_id="gpt-image-2",
        provider_config=SimpleNamespace(api_key_ciphertext="encrypted", base_url="https://api.openai.com/v1"),
    )
    request = ImageGenerationInput(
        operation="edit",
        prompt="调整颜色",
        aspect_ratio="1:1",
        resolution_tier="standard",
        quality="medium",
        count=1,
        references=[("source.png", "image/png", b"source")],
        advanced_options={"output_format": "jpeg", "output_compression": 80, "moderation": "auto"},
    )

    result = await adapter.submit(config, get_image_model_spec("openai_image", "gpt-image-2"), request)

    assert "moderation" not in captured
    assert captured["output_format"] == "jpeg"
    assert result.images[0].content_type == "image/jpeg"

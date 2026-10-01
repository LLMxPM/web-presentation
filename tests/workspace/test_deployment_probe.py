"""文件功能：验证完整部署探针严格检查任务、页面版本及下载内容，测试中不访问服务。"""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from test_image_evidence import png


@pytest.mark.parametrize("failure", [None, "stale_page", "bad_zip", "failed_job"])
def test_pipeline_evidence_requires_all_stages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: str | None
) -> None:
    """任一阶段失败都保留失败摘要及任务 ID，不能输出 passed 或泄露下载 URL。"""
    directory = Path(__file__).resolve().parents[2] / "scripts/contracts"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location(
        "deployment_probe", directory / "check-deployment-pipeline.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("index.html", '<html><script src="main.js"></script></html>')
        archive.writestr("main.js", "document.body.textContent='test'")
    content = buffer.getvalue()
    image = png()
    page = {
        "workspace_id": 1,
        "screenshot_is_latest": failure != "stale_page",
        "screenshot_version_no": 2,
        "screenshot_url": "/storage/test.png?token=must-not-be-recorded",
    }
    screenshot = {
        "id": 3,
        "target_page_version_no": 2,
        "viewport_width": 320,
        "viewport_height": 240,
    }
    build = {
        "id": 4,
        "artifact_sha256": "wrong"
        if failure == "bad_zip"
        else hashlib.sha256(content).hexdigest(),
        "artifact_size_bytes": len(content),
        "artifact_entry_file": "index.html",
    }

    class Client:
        """按真实路径返回测试响应，任何未声明路径直接失败。"""

        def json(self, path, payload=None):
            """校验探针创建截图和构建时的正式请求体。"""
            if path == "api/pages/1/screenshot-jobs":
                assert payload in ({}, {"viewport_width": 320, "viewport_height": 240})
            if path == "api/projects/2/build-jobs":
                assert payload == {"base_url": "./"}
            return {
                "api/projects/2": {"workspace_id": 1},
                "api/pages/1": page,
                "api/pages/1/screenshot-jobs": screenshot,
                "api/projects/2/build-jobs": build,
            }[path]

        def wait_job(self, path, _timeout):
            """模拟队列失败，验证后续下载不会掩盖失败。"""
            if failure == "failed_job":
                raise RuntimeError("任务失败")
            return {
                "api/pages/screenshot-jobs/3": screenshot,
                "api/build-jobs/4": build,
            }[path]

        def fetch(self, path, **_kwargs):
            """只允许正式截图 URL 与指定项目构建下载路径。"""
            return {
                page["screenshot_url"]: image,
                "api/projects/2/build-jobs/4/artifact": content,
            }[path]

    output = tmp_path / "evidence"
    if failure:
        with pytest.raises((ValueError, RuntimeError)):
            module.verify_pipeline(
                Client(), page_id=1, project_id=2, output=output, timeout=1
            )
    else:
        module.verify_pipeline(
            Client(), page_id=1, project_id=2, output=output, timeout=1
        )
        assert (output / "build.zip").read_bytes() == content
        assert (output / "page.png").read_bytes() == image
    text = (output / "pipeline.json").read_text(encoding="utf-8")
    assert json.loads(text)["status"] == ("failed" if failure else "passed")
    assert json.loads(text)["screenshot_job_id"] == 3
    assert "must-not-be-recorded" not in text

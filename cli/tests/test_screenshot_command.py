"""文件功能：测试 CLI 页面最新截图命令 (wp screenshot / wp page screenshot) 的同源安全、单次 GET 请求与原子文件落盘。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 确保能定位到 cli/src
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from click.testing import CliRunner
from wp.cli import main
from wp.client import ApiClient, ApiClientError
from wp.config import ProfileConfig


def test_screenshot_command_help() -> None:
    """测试 screenshot 命令帮助信息。"""

    runner = CliRunner()
    result = runner.invoke(main, ["screenshot", "--help"])
    assert result.exit_code == 0
    assert "获取指定页面的最新截图" in result.output


def test_screenshot_command_success(tmp_path: Path) -> None:
    """测试成功获取最新截图并原子保存至指定路径。"""

    runner = CliRunner()
    output_file = tmp_path / "test_output.png"

    fake_meta = {"page_id": 42, "version_no": 3}
    fake_img_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR_FAKE_BYTES"

    mock_client = MagicMock()
    mock_client.get_latest_page_screenshot.return_value = (fake_meta, fake_img_bytes)

    with patch("wp.commands.screenshot.ApiClient", return_value=mock_client):
        result = runner.invoke(main, ["screenshot", "42", "--output", str(output_file)])

    assert result.exit_code == 0
    assert output_file.exists()
    assert output_file.read_bytes() == fake_img_bytes
    assert "成功获取页面 (ID: 42) 最新截图" in result.output
    mock_client.get_latest_page_screenshot.assert_called_once_with(page_id=42)


def test_screenshot_command_json_mode(tmp_path: Path) -> None:
    """测试以 --json 模式输出最新截图元数据。"""

    runner = CliRunner()
    output_file = tmp_path / "json_test.png"

    fake_meta = {"page_id": 10, "version_no": 2}
    fake_img_bytes = b"FAKE_PNG_CONTENT"

    mock_client = MagicMock()
    mock_client.get_latest_page_screenshot.return_value = (fake_meta, fake_img_bytes)

    with patch("wp.commands.screenshot.ApiClient", return_value=mock_client):
        result = runner.invoke(main, ["--json", "screenshot", "10", "--output", str(output_file)])

    assert result.exit_code == 0
    assert output_file.exists()

    parsed = json.loads(result.output)
    assert parsed["page_id"] == 10
    assert parsed["version_no"] == 2
    assert parsed["size_bytes"] == len(fake_img_bytes)


def test_client_get_bytes_same_origin_security() -> None:
    """测试 ApiClient.get_bytes 对非同源绝对 URL 的 PAT 拦截机制。"""

    profile = ProfileConfig(endpoint="http://127.0.0.1:8000", token="pat_secret_123")
    client = ApiClient(profile)

    # 1. 同源绝对路径 -> 允许发送
    assert client._is_same_origin("http://127.0.0.1:8000/api/v1/pages/1/screenshot") is True

    # 2. 外部恶意域名 -> 拒绝并引发 ApiClientError
    assert client._is_same_origin("https://evil-third-party.com/steal-token") is False

    with pytest.raises(ApiClientError) as exc_info:
        client.get_bytes("https://evil-third-party.com/steal-token")

    assert exc_info.value.code == "CROSS_ORIGIN_PAT_BLOCKED"
    assert "禁止向非 Endpoint 同源地址发送 PAT 令牌" in exc_info.value.message


def test_client_get_latest_page_screenshot_single_get_request() -> None:
    """测试 ApiClient.get_latest_page_screenshot 发起一次性 GET 请求与 Header 解析。"""

    profile = ProfileConfig(endpoint="http://127.0.0.1:8000", token="pat_secret_123")
    client = ApiClient(profile)

    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.headers = {"x-page-id": "123", "x-page-version-no": "5", "content-type": "image/png"}
    mock_response.content = b"\x89PNG_SINGLE_GET"

    with patch.object(client.client, "get", return_value=mock_response) as mock_get:
        meta, img_bytes = client.get_latest_page_screenshot(123)

    assert meta["page_id"] == 123
    assert meta["version_no"] == 5
    assert img_bytes == b"\x89PNG_SINGLE_GET"

    mock_get.assert_called_once()
    url = mock_get.call_args[0][0]
    assert url == "/api/v1/pages/123/screenshot"


def test_client_get_latest_page_screenshot_strict_validations() -> None:
    """测试当响应 Content-Type 或 X-Page-Version-No 响应头异常时进行严格拦截。"""

    profile = ProfileConfig(endpoint="http://127.0.0.1:8000", token="pat_secret_123")
    client = ApiClient(profile)

    # 1. 非 image/png Content-Type (如 HTML 错误页)
    bad_ct_response = MagicMock()
    bad_ct_response.is_success = True
    bad_ct_response.headers = {"x-page-version-no": "1", "content-type": "text/html"}
    bad_ct_response.content = b"<html>502 Gateway Error</html>"

    with patch.object(client.client, "get", return_value=bad_ct_response):
        with pytest.raises(ApiClientError) as exc_info:
            client.get_latest_page_screenshot(1)
        assert exc_info.value.code == "INVALID_CONTENT_TYPE"
        assert "预期为 image/png" in exc_info.value.message

    # 2. 缺少 X-Page-Version-No 响应头
    missing_hdr_response = MagicMock()
    missing_hdr_response.is_success = True
    missing_hdr_response.headers = {"content-type": "image/png"}
    missing_hdr_response.content = b"PNG"

    with patch.object(client.client, "get", return_value=missing_hdr_response):
        with pytest.raises(ApiClientError) as exc_info:
            client.get_latest_page_screenshot(1)
        assert exc_info.value.code == "INVALID_HEADER"
        assert "X-Page-Version-No" in exc_info.value.message

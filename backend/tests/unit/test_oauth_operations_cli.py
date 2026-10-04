"""文件功能：验证 OAuth 运维 CLI 的 Secret 文件边界、失败脱敏及后台清理取消行为。"""

import asyncio
import json
from pathlib import Path

import pytest
from app.scripts import oauth_cleanup, oauth_services
from app.services.oauth import cleanup_service


def test_secret_file_reads_only_one_trailing_newline_and_rejects_oversize(
    tmp_path: Path,
):
    """常见 Secret 文件末尾换行可读取，内部空白不能被无条件 strip 掩盖。"""
    secret_file = tmp_path / "service-secret"
    secret_file.write_bytes(b"service-secret-value\r\n")
    assert oauth_services.read_service_secret(secret_file) == "service-secret-value"
    secret_file.write_bytes(b" service-secret-value \n\n")
    assert oauth_services.read_service_secret(secret_file) == " service-secret-value \n"
    secret_file.write_bytes(b"a" * 1025)
    with pytest.raises(ValueError):
        oauth_services.read_service_secret(secret_file)


def test_service_cli_does_not_accept_secret_in_arguments():
    """明文密钥不能通过命令行 flag 进入进程参数；登记必须提供 Secret 文件。"""
    parser = oauth_services.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["create", "--service-id", "new-mcp", "--name", "服务", "--secret", "raw"]
        )
    args = parser.parse_args(
        ["rotate", "--service-id", "new-mcp", "--secret-file", "secret"]
    )
    assert args.enable is False


@pytest.mark.parametrize(
    "module,argv", [(oauth_services, ["list"]), (oauth_cleanup, [])]
)
def test_cli_failure_never_prints_exception_payload_or_credentials(
    module, argv, monkeypatch, capsys
):
    """数据库错误或 Secret 解码错误不能把原始异常参数带入 stderr。"""

    async def fail(args):
        """模拟包含敏感字符串的底层异常。"""
        raise RuntimeError("postgresql://user:password@private/db wp_ort_raw-secret")

    monkeypatch.setattr(module, "run_command", fail)
    assert module.main(argv) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "RuntimeError" in output.err
    assert "password" not in output.err and "wp_ort_" not in output.err


def test_cleanup_cli_defaults_to_bounded_read_only_preview(monkeypatch, capsys):
    """省略 --apply 时 CLI 只能做预检，批次默认 200，实际提交需明确执行标识。"""
    received = []

    async def run(args):
        """截取解析后的参数，不创建数据库连接。"""
        received.append((args.apply, args.batch_size))
        return {"dry_run": not args.apply}

    monkeypatch.setattr(oauth_cleanup, "run_command", run)
    assert oauth_cleanup.main([]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert oauth_cleanup.main(["--apply", "--batch-size", "25"]) == 0
    assert received == [(False, 200), (True, 25)]


@pytest.mark.parametrize("batch_size", [0, 1001, True])
def test_cleanup_rejects_unbounded_batch(batch_size):
    """清理服务在连库前拒绝无效批次，不能变成无界全表删除。"""
    with pytest.raises(ValueError):
        cleanup_service.OAuthCleanupService(lambda: None, batch_size=batch_size)


async def test_background_cleanup_retries_safely_and_propagates_cancellation(
    monkeypatch, caplog
):
    """失败日志不包含秘密，下一轮继续；取消穿透 Exception 捕获且不启动下一轮。"""
    calls, intervals = [], []

    async def sweep(self):
        """第一轮抛出带敏感数据的异常，第二轮模拟有界清理成功。"""
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("wp_oat_hidden-sensitive-value")
        return {"codes": 1}

    async def sleep(seconds):
        """替代计时，不让测试实际等待五分钟；第二次等待模拟应用关闭。"""
        intervals.append(seconds)
        if len(intervals) == 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr(cleanup_service.OAuthCleanupService, "sweep", sweep)
    monkeypatch.setattr(cleanup_service.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await cleanup_service.run_oauth_cleanup_loop(lambda: None)
    assert len(calls) == 2 and intervals == [300, 300]
    assert "wp_oat_" not in caplog.text and "清理失败" in caplog.text

"""文件功能：以真实隔离数据库验证 OAuth 运维 CLI 的配置、Secret 文件及预检调用链。"""

from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

from app.models.oauth_registration import OAuthMcpService
from app.scripts import oauth_cleanup, oauth_services
from sqlalchemy import select

from tests.fixtures.oauth import POLICY


async def test_service_cli_uses_explicit_policy_and_secret_file(
    oauth_database, monkeypatch, tmp_path: Path
):
    """CLI 复用根配置校验，登记 Secret 文件的哈希，列表和停用只返回公共元数据。"""
    settings = SimpleNamespace(
        oauth_enabled=True,
        oauth_issuer=POLICY.issuer,
        oauth_mcp_resource=POLICY.mcp_resource,
        oauth_api_audience=POLICY.api_audience,
        oauth_editor_origin=POLICY.issuer,
        session_secure=True,
        cors_origins=[],
    )
    monkeypatch.setattr(oauth_services, "get_settings", lambda: settings)
    monkeypatch.setattr(oauth_services, "get_session_factory", lambda: oauth_database)
    secret_file = tmp_path / "service-secret"
    secret_file.write_text("test-service-secret-" * 3 + "\n", encoding="ascii")
    parser = oauth_services.build_parser()
    created = await oauth_services.run_command(
        parser.parse_args(
            [
                "create",
                "--service-id",
                "cli-mcp",
                "--name",
                "CLI 服务",
                "--secret-file",
                str(secret_file),
            ]
        )
    )
    assert created["resource"] == POLICY.mcp_resource
    assert await oauth_services.run_command(parser.parse_args(["list"])) == [created]
    disabled = await oauth_services.run_command(
        parser.parse_args(["disable", "--service-id", "cli-mcp"])
    )
    assert disabled["is_active"] is False
    async with oauth_database() as session:
        service = await session.scalar(select(OAuthMcpService))
        assert "secret_hash" not in disabled and service.secret_hash not in repr(
            disabled
        )


async def test_cleanup_cli_preview_and_apply_use_independent_database(
    oauth_database, monkeypatch
):
    """关闭 OAuth 也可运行预检及提交；CLI 只公开批次数量，无凭证列表。"""
    monkeypatch.setattr(oauth_cleanup, "get_session_factory", lambda: oauth_database)
    result = await oauth_cleanup.run_command(Namespace(apply=False, batch_size=1))
    assert result["dry_run"] is True and result["batch_size"] == 1
    assert set(result) == {"dry_run", "batch_size", "counts"}
    assert not any(result["counts"].values())
    assert (await oauth_cleanup.run_command(Namespace(apply=True, batch_size=1)))[
        "dry_run"
    ] is False

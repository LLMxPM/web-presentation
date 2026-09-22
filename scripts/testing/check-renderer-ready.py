"""文件功能：使用 Backend 真实 HTTP 客户端验证 E2E Renderer 的身份与协议，不连接业务数据库。"""
import asyncio

from app.core.config import get_settings
from app.services.rendering.client import RendererClient
from app.services.rendering.target_resolver import WorkerEndpoint


async def main() -> None:
    """校验唯一测试 Worker 的认证、ID 与协议，失败直接以非零退出码中止准备。"""

    settings = get_settings()
    worker = settings.render_workers_config[0]
    endpoint = WorkerEndpoint(worker_id=worker["worker_id"], base_url=worker["base_url"])
    capabilities = await RendererClient().fetch_capabilities(endpoint)
    if capabilities.worker_id != endpoint.worker_id:
        raise RuntimeError("Renderer Worker ID 不符合测试配置。")
    if capabilities.render_profile_digest != settings.render_profile_digest:
        raise RuntimeError("Renderer profile 不符合测试配置。")
    print("[testing] Renderer 服务身份与协议校验通过")


if __name__ == "__main__":
    asyncio.run(main())

"""文件功能：提供平台测试场景的数据库初始化、烟雾数据注入和重置能力。"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg
from sqlalchemy import select, text
from sqlalchemy.engine import make_url

import app.models  # noqa: F401
from app.schemas.model_config import (
    ChatBindingUpdate, ChatModelConfigCreate, ChatProviderConfigCreate,
    ImageBindingUpdate, ImageModelConfigCreate, ImageProviderConfigCreate,
)
from app.schemas.page import PageCreateRequest
from app.schemas.project import ProjectCreateRequest
from app.schemas.project_route import ProjectRouteItemWrite, ProjectRouteTreeWriteRequest
from app.schemas.workspace import WorkspaceCreateRequest
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_engine, get_session_factory
from app.models.asset import WorkspaceAsset
from app.models.enums import AiLlmSlot, AssetType
from app.models.user import User
from app.models.page import Page
from app.models.workspace import Project, Workspace
from app.services.ai_chat_config_service import AiChatConfigService
from app.services.ai_image_config_service import AiImageConfigService
from app.services.ai_model_catalog_service import AiModelCatalogService
from app.services.asset_service import AssetService
from app.services.bootstrap_service import BootstrapService
from app.services.page_service import PageService
from app.services.project_route_service import ProjectRouteService
from app.services.project_service import ProjectService
from app.services.workspace_service import WorkspaceService

E2E_DATABASE_MARKER = "_e2e"
POSTGRES_MAINTENANCE_DATABASE = "postgres"
# smoke 数据协议版本：seed 结构变化时递增，ensure-services 据此校验环境指纹。
SEED_VERSION = 2


@dataclass(slots=True, frozen=True)
class SmokeDataNames:
    """统一维护 smoke 场景使用的固定名称，避免前后端 fixture 漂移。"""

    workspace_name: str = "Smoke Workspace"
    project_name: str = "Smoke Project"
    page_title: str = "Smoke Page"
    agent_llm_config_name: str = "Smoke E2E Mock Agent"
    vision_llm_config_name: str = "Smoke E2E Mock Vision"
    image_llm_config_name: str = "Smoke E2E Mock Image"
    page_summary: str = "平台级 smoke 场景默认页面。"
    image_asset_a: str = "smoke-image-a"
    image_asset_b: str = "smoke-image-b"


SMOKE_DATA = SmokeDataNames()
DEFAULT_SMOKE_PAGE_CONTENT = """<template>
  <main class="smoke-page">
    <h1 class="text-4xl font-black text-center leading-tight text-slate-900">Smoke Page</h1>
    <p>platform smoke preview</p>
    <AssetImage
      name="smoke-image-a"
      alt="Smoke illustration"
      fit="contain"
      position="center"
      class="w-48 h-32 p-2 bg-white border rounded-lg"
    />
    <ul>
      <li v-for="item in items" :key="item.id">{{ item.label }}</li>
    </ul>
  </main>
</template>

<script setup lang="ts">
import AssetImage from '@runtime-kit/public/components/assets/AssetImage.v1.vue'

const items = [
  { id: 'smoke-1', label: 'first item' },
  { id: 'smoke-2', label: 'second item' },
]
</script>

<style scoped>
.smoke-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: #f8fafc;
  color: #0f172a;
}
</style>
"""


async def ensure_database_schema() -> None:
    """确保测试脚本运行前数据库表已就绪。"""

    await ensure_configured_database_exists()
    engine = get_engine()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def reset_all_test_data() -> None:
    """重建全部业务表，供 smoke 场景在本地或 CI 中回到干净状态。"""

    require_e2e_database_url()
    await ensure_configured_database_exists()
    engine = get_engine()
    async with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            # E2E 库由 create_all 演进而非 alembic 迁移，旧版模型残留的外键约束
            # 不在当前 metadata 依赖图中；带 CASCADE 逐表删除可避免孤儿约束阻断重建。
            for table in reversed(Base.metadata.sorted_tables):
                await connection.execute(text(f'DROP TABLE IF EXISTS "{table.name}" CASCADE'))
        else:
            await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    await BootstrapService(get_session_factory()).ensure_default_admin()


async def ensure_smoke_data() -> None:
    """为平台级 smoke 测试创建最小可用的工作空间、项目、页面和 AI mock 绑定。"""

    await ensure_database_schema()
    await BootstrapService(get_session_factory()).ensure_default_admin()

    async with get_session_factory()() as session:
        seed_user = await session.scalar(select(User).order_by(User.id.asc()).limit(1))
        if seed_user is None:
            raise RuntimeError("默认管理员初始化失败。")

        workspace = await _ensure_workspace(session=session, operator_id=seed_user.id)
        await _ensure_smoke_image_assets(session=session, workspace_id=workspace.id)
        project = await _ensure_project(session=session, workspace_id=workspace.id, operator_id=seed_user.id)
        page = await _ensure_page(
            session=session,
            workspace_id=workspace.id,
            project_id=project.id,
            operator_id=seed_user.id,
        )
        await _ensure_project_routes(session=session, project_id=project.id, page_id=page.id, operator_id=seed_user.id)
        await _ensure_mock_llm_binding(session=session, user_id=seed_user.id, operator_id=seed_user.id)


async def _ensure_workspace(*, session, operator_id: int) -> Workspace:
    workspace = await session.scalar(select(Workspace).where(Workspace.name == SMOKE_DATA.workspace_name))
    if workspace is not None:
        return workspace

    created = await WorkspaceService(session).create(
        WorkspaceCreateRequest(
            name=SMOKE_DATA.workspace_name,
            description="平台级 smoke 测试工作空间。",
        ),
        operator_id,
    )
    workspace = await session.get(Workspace, created.id)
    if workspace is None:
        raise RuntimeError("工作空间创建后未能重新加载。")
    return workspace


async def _ensure_project(*, session, workspace_id: int, operator_id: int) -> Project:
    statement = select(Project).where(
        Project.workspace_id == workspace_id,
        Project.name == SMOKE_DATA.project_name,
    )
    project = await session.scalar(statement)
    if project is not None:
        return project

    created = await ProjectService(session).create(
        ProjectCreateRequest(
            workspace_id=workspace_id,
            name=SMOKE_DATA.project_name,
            description="平台级 smoke 测试项目。",
        ),
        operator_id,
    )
    project = await session.get(Project, created.id)
    if project is None:
        raise RuntimeError("项目创建后未能重新加载。")
    return project


async def _ensure_page(*, session, workspace_id: int, project_id: int, operator_id: int) -> Page:
    statement = select(Page).where(
        Page.workspace_id == workspace_id,
        Page.project_id == project_id,
        Page.title == SMOKE_DATA.page_title,
    )
    page = await session.scalar(statement)
    if page is not None:
        return page

    created = await PageService(session).create(
        PageCreateRequest(
            workspace_id=workspace_id,
            project_id=project_id,
            title=SMOKE_DATA.page_title,
            summary=SMOKE_DATA.page_summary,
            page_content=DEFAULT_SMOKE_PAGE_CONTENT,
        ),
        operator_id,
    )
    page = await session.get(Page, created.id)
    if page is None:
        raise RuntimeError("页面创建后未能重新加载。")
    return page


async def _ensure_smoke_image_assets(*, session, workspace_id: int) -> None:
    """创建两张可区分的 SVG 图片，供可视化编辑资源替换 E2E 使用。"""

    assets = (
        (
            SMOKE_DATA.image_asset_a,
            "smoke-image-a.svg",
            '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180">'
            '<rect width="320" height="180" rx="24" fill="#4f46e5"/>'
            '<circle cx="160" cy="90" r="48" fill="#ffffff"/>'
            "</svg>",
        ),
        (
            SMOKE_DATA.image_asset_b,
            "smoke-image-b.svg",
            '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180">'
            '<rect width="320" height="180" rx="24" fill="#0f766e"/>'
            '<path d="M80 125L140 55l40 45 35-35 45 60z" fill="#ffffff"/>'
            "</svg>",
        ),
    )
    service = AssetService(session)
    for name, original_name, content in assets:
        existing = await session.scalar(
            select(WorkspaceAsset).where(
                WorkspaceAsset.workspace_id == workspace_id,
                WorkspaceAsset.name == name,
            )
        )
        if existing is not None:
            continue
        await service.create_content_asset(
            workspace_id,
            asset_type=AssetType.IMAGE,
            name=name,
            original_name=original_name,
            content=content,
            tags=["smoke", "visual-edit"],
            description="可视化编辑 E2E 图片资源。",
        )


async def _ensure_project_routes(*, session, project_id: int, page_id: int, operator_id: int) -> None:
    route_service = ProjectRouteService(session)
    existing_tree = await route_service.get_tree(project_id)
    if existing_tree.routes:
        return

    await route_service.replace_tree(
        project_id,
        ProjectRouteTreeWriteRequest(
            routes=[
                ProjectRouteItemWrite(
                    route_type="page",
                    route="home",
                    order=1,
                    page_id=page_id,
                )
            ]
        ),
        operator_id,
    )


async def _ensure_mock_llm_binding(*, session, user_id: int, operator_id: int) -> None:
    if get_settings().ai_test_mode != "mock":
        return

    await AiModelCatalogService(session).ensure_minimal_catalog()
    chat = AiChatConfigService(session, user_id=user_id, user_role="workspace_user")
    image = AiImageConfigService(session, user_id=user_id, user_role="workspace_user")
    chat_provider = next((item for item in await chat.list_providers() if item.name == "OpenAI Mock 凭证"), None)
    if chat_provider is None:
        chat_provider = await chat.create_provider(
            ChatProviderConfigCreate(name="OpenAI Mock 凭证", catalog_provider_key="openai"), operator_id=operator_id
        )
    chat_models = await chat.list_models()
    agent_config = next((item for item in chat_models if item.name == SMOKE_DATA.agent_llm_config_name), None)
    if agent_config is None:
        agent_config = await chat.create_model(ChatModelConfigCreate(
            name=SMOKE_DATA.agent_llm_config_name, provider_config_id=chat_provider.id,
            model_id="e2e-mock-agent-chat", capability_override={"supports_tool_call": True},
        ), operator_id=operator_id)
    vision_config = next((item for item in chat_models if item.name == SMOKE_DATA.vision_llm_config_name), None)
    if vision_config is None:
        vision_config = await chat.create_model(ChatModelConfigCreate(
            name=SMOKE_DATA.vision_llm_config_name, provider_config_id=chat_provider.id,
            model_id="e2e-mock-vision-chat", capability_override={"supports_tool_call": True, "supports_image_input": True},
        ), operator_id=operator_id)
    await chat.update_binding(AiLlmSlot.AGENT_COORDINATOR.value,
        ChatBindingUpdate(model_config_id=agent_config.id), operator_id=operator_id)
    await chat.update_binding(AiLlmSlot.IMAGE_UNDERSTANDING.value,
        ChatBindingUpdate(model_config_id=vision_config.id), operator_id=operator_id)

    image_provider = next((item for item in await image.list_providers() if item.name == "OpenAI Mock 图片凭证"), None)
    if image_provider is None:
        image_provider = await image.create_provider(
            ImageProviderConfigCreate(name="OpenAI Mock 图片凭证", provider_key="openai_image"), operator_id=operator_id
        )
    image_config = next((item for item in await image.list_models() if item.name == SMOKE_DATA.image_llm_config_name), None)
    if image_config is None:
        image_config = await image.create_model(ImageModelConfigCreate(
            name=SMOKE_DATA.image_llm_config_name, provider_config_id=image_provider.id, model_id="e2e-mock-image-gen"
        ), operator_id=operator_id)
    await image.update_binding(ImageBindingUpdate(model_config_id=image_config.id), operator_id=operator_id)


def require_e2e_database_url() -> None:
    """限制重置脚本只能作用于名称包含 _e2e 的数据库。"""

    database_name = extract_database_name(get_settings().database_url)
    if E2E_DATABASE_MARKER not in database_name:
        raise RuntimeError(
            f"拒绝重置非 E2E 数据库：当前数据库名为 {database_name or '<unknown>'}，"
            f"必须包含 {E2E_DATABASE_MARKER}。"
        )


async def ensure_configured_database_exists() -> None:
    """为 PostgreSQL E2E 默认库自动建库，避免 CI 初始化库名和测试库名耦合。"""

    settings = get_settings()
    url = make_url(settings.database_url)
    if not url.drivername.startswith("postgresql"):
        return

    target_database = url.database or ""
    if not target_database:
        raise RuntimeError("DATABASE_URL 缺少数据库名。")
    if E2E_DATABASE_MARKER not in target_database:
        return
    if target_database == POSTGRES_MAINTENANCE_DATABASE:
        return
    if await can_connect_to_postgres_database(url, target_database):
        return

    connection = await asyncpg.connect(**build_asyncpg_connection_kwargs(url, POSTGRES_MAINTENANCE_DATABASE))
    try:
        exists = await connection.fetchval("select 1 from pg_database where datname = $1", target_database)
        if exists:
            return
        await connection.execute(f"create database {quote_postgres_identifier(target_database)}")
    finally:
        await connection.close()


async def can_connect_to_postgres_database(url, database_name: str) -> bool:
    """检查目标 PostgreSQL 数据库是否已经存在且可连接。"""

    try:
        connection = await asyncpg.connect(**build_asyncpg_connection_kwargs(url, database_name))
    except asyncpg.InvalidCatalogNameError:
        return False

    await connection.close()
    return True


def build_asyncpg_connection_kwargs(url, database_name: str) -> dict[str, object]:
    """从 SQLAlchemy URL 提取 asyncpg 连接参数。"""

    return {
        "user": url.username,
        "password": url.password,
        "host": url.host or "127.0.0.1",
        "port": url.port or 5432,
        "database": database_name,
    }


def extract_database_name(database_url: str) -> str:
    """从 SQLAlchemy URL 中提取数据库名，供危险操作校验使用。"""

    return make_url(database_url).database or ""


def quote_postgres_identifier(value: str) -> str:
    """转义 PostgreSQL 标识符，避免建库语句受特殊字符影响。"""

    return '"' + value.replace('"', '""') + '"'

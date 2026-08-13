"""文件功能：在协议拆分升级窗口中显式清空 AI 运行记录及 Chat/Image 用户配置。"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text

from app.db.session import get_session_factory

CONFIRMATION = "RESET_AI_CONFIGURATION"
TABLES_IN_DELETE_ORDER = (
    "ai_image_generation_jobs",
    "ai_page_mutation_jobs",
    "ai_page_mutation_batches",
    "ai_agent_requirements",
    "ai_agent_tool_calls",
    "ai_agent_messages",
    "ai_agent_run_events",
    "ai_agent_member_runs",
    "ai_agent_runs",
    "ai_agent_sessions",
    "ai_agent_image_attachments",
    "ai_image_slot_bindings",
    "ai_image_model_configs",
    "ai_image_provider_configs",
    "ai_chat_slot_bindings",
    "ai_chat_model_configs",
    "ai_chat_provider_configs",
)


async def reset_ai_configuration() -> None:
    """按外键顺序删除 AI 运行态和用户模型配置，不删除业务数据与图片文件。"""

    async with get_session_factory()() as session:
        async with session.begin():
            for table in TABLES_IN_DELETE_ORDER:
                await session.execute(text(f"DELETE FROM {table}"))


def main() -> None:
    """要求部署人员传入固定确认串，降低误执行风险。"""

    parser = argparse.ArgumentParser(description="清空 AI 运行记录及 Chat/Image 用户配置。")
    parser.add_argument("--confirm", required=True, help=f"必须填写 {CONFIRMATION}")
    args = parser.parse_args()
    if args.confirm != CONFIRMATION:
        parser.error("确认串不匹配，未执行任何删除。")
    asyncio.run(reset_ai_configuration())
    print("AI 运行记录及 Chat/Image 用户配置已清空；业务数据、目录缓存和图片文件未删除。")


if __name__ == "__main__":
    main()

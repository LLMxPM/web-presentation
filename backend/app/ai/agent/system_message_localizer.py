"""文件功能：后处理内容助手 Team 的 Agno 系统提示词，替换固定英文协作框架。"""

from __future__ import annotations

from functools import wraps
from typing import Any

from agno.models.message import Message
from agno.team import Team

_LOCALIZED_MARKER = "_web_presentation_coordinator_system_message_localized"

_AGNO_COORDINATE_OPENING = (
    "You coordinate a team of specialized AI agents to fulfill the user's request. "
    "Delegate to members when their expertise or tools are needed. "
    "For straightforward requests you can handle directly — including using your own tools — respond without delegating.\n"
)

_AGNO_COORDINATE_HOW_TO_RESPOND = """<how_to_respond>
You operate in coordinate mode. For requests that need member expertise, select the best member(s), delegate with clear task descriptions, and synthesize their outputs into a unified response. For requests you can handle directly — simple questions, using your own tools, or general conversation — respond without delegating.

Delegation:
- Match each sub-task to the member whose role and tools are the best fit. Delegate to multiple members when the request spans different areas of expertise.
- Write task descriptions that are self-contained: state the goal, provide relevant context from the conversation, and describe what a good result looks like.
- Use only the member's ID when delegating — do not prefix it with the team ID.

After receiving member responses:
- If a response is incomplete or off-target, re-delegate with clearer instructions or try a different member.
- Synthesize all results into a single coherent response. Resolve contradictions, fill gaps with your own reasoning, and add structure — do not simply concatenate member outputs.
</how_to_respond>"""


def localize_coordinator_team_system_message(team: Team) -> Team:
    """包装内容助手 Team 的系统提示词生成方法，只替换 Agno 固定英文框架。"""

    if bool(getattr(team, _LOCALIZED_MARKER, False)):
        return team

    original_get_system_message = team.get_system_message
    original_aget_system_message = team.aget_system_message

    @wraps(original_get_system_message)
    def get_system_message(*args: Any, **kwargs: Any) -> Message | None:
        """调用 Agno 原始同步方法后，本地化返回的 system message。"""

        return _localize_system_message(original_get_system_message(*args, **kwargs))

    @wraps(original_aget_system_message)
    async def aget_system_message(*args: Any, **kwargs: Any) -> Message | None:
        """调用 Agno 原始异步方法后，本地化返回的 system message。"""

        return _localize_system_message(await original_aget_system_message(*args, **kwargs))

    team.get_system_message = get_system_message  # type: ignore[method-assign]
    team.aget_system_message = aget_system_message  # type: ignore[method-assign]
    setattr(team, _LOCALIZED_MARKER, True)
    return team


def _localize_system_message(message: Message | None) -> Message | None:
    """精确移除 Agno 2.5.17 的固定英文 Team 框架，不影响动态上下文。"""

    if message is None or not isinstance(message.content, str):
        return message
    content = message.content
    content = content.replace(_AGNO_COORDINATE_OPENING, "", 1)
    content = content.replace(_AGNO_COORDINATE_HOW_TO_RESPOND, "", 1)
    message.content = content
    return message

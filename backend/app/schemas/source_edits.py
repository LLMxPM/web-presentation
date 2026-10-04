"""文件功能：统一 AI 工具和 External API 的结构化源码编辑 Schema，禁止任意编辑对象。"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

SourceEditType = Literal["replace_exact", "insert_after", "rewrite_file"]


class _SourceEditBase(BaseModel):
    """编辑对象禁止额外字段，定位文本必须来自当前源码。"""

    model_config = ConfigDict(extra="forbid")


class ReplaceExactEdit(_SourceEditBase):
    """精确替换唯一命中的 old_text，new_text 为空表示删除。"""

    type: Literal["replace_exact"] = Field(description="精确替换唯一命中的 old_text。")
    old_text: str = Field(min_length=1, description="来自读取工具返回的真实源码片段，必须唯一命中。")
    new_text: str = Field(description="替换后的源码片段；允许为空字符串以删除内容。")


class InsertAfterEdit(_SourceEditBase):
    """在唯一命中的 anchor_text 后插入非空 new_text。"""

    type: Literal["insert_after"] = Field(description="在唯一命中的 anchor_text 后插入内容。")
    anchor_text: str = Field(min_length=1, description="来自读取工具返回的真实源码片段，必须唯一命中。")
    new_text: str = Field(min_length=1, description="要插入的源码片段。")


class RewriteFileEdit(_SourceEditBase):
    """以完整非空 content 重写源码文件。"""

    type: Literal["rewrite_file"] = Field(description="用完整 content 重写整个源码文件。")
    content: str = Field(min_length=1, description="完整的新源码内容。")


SourceEditInput = Annotated[
    ReplaceExactEdit | InsertAfterEdit | RewriteFileEdit,
    Field(discriminator="type"),
]

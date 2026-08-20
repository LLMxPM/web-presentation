"""文件功能：管理 CLI 本地配置文件与多 Profile 切换（存储在 ~/.web-presentation/config.json）。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

CONFIG_DIR = Path.home() / ".web-presentation"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_PROFILE = "default"
DEFAULT_ENDPOINT = "http://127.0.0.1:8000"


class ProfileConfig(BaseModel):
    """单个环境 Profile 配置项。"""

    endpoint: str = Field(default=DEFAULT_ENDPOINT)
    token: str | None = Field(default=None)
    default_workspace_id: int | None = Field(default=None)


class CliConfig(BaseModel):
    """CLI 全局配置文件。"""

    current_profile: str = Field(default=DEFAULT_PROFILE)
    profiles: dict[str, ProfileConfig] = Field(
        default_factory=lambda: {DEFAULT_PROFILE: ProfileConfig()}
    )


def load_config() -> CliConfig:
    """加载本地配置文件；若不存在则自动初始化默认配置。"""

    if not CONFIG_FILE.exists():
        return CliConfig()

    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return CliConfig.model_validate(data)
    except Exception:
        return CliConfig()


def save_config(config: CliConfig) -> None:
    """持久化保存本地配置文件（在 POSIX 系统上设置 0600 权限防止凭据泄露）。"""

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    content = json.dumps(config.model_dump(mode="json"), indent=2, ensure_ascii=False)
    CONFIG_FILE.write_text(content, encoding="utf-8")
    if os.name != "nt":
        try:
            CONFIG_FILE.chmod(0o600)
        except Exception:
            pass


def get_profile(config: CliConfig, profile_name: str | None = None) -> ProfileConfig:
    """获取指定或当前的 Profile 配置。"""

    name = profile_name or config.current_profile or DEFAULT_PROFILE
    if name not in config.profiles:
        config.profiles[name] = ProfileConfig()
    return config.profiles[name]

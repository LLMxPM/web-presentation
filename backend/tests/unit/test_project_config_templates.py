"""文件功能：验证 Backend 默认项目配置模板的读取位置、内容完整性与 YAML 可解析性。"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.services.project_config_service import (
    CONFIG_FILE_MAP,
    PROJECT_CONFIG_TEMPLATE_ROOT,
    load_default_project_config_templates,
)


def test_default_project_config_templates_should_be_backend_owned() -> None:
    """默认项目配置模板应由 Backend 自己携带，避免生产镜像依赖 Runtime 目录。"""

    backend_root = Path(__file__).resolve().parents[2]

    assert PROJECT_CONFIG_TEMPLATE_ROOT == backend_root / "app" / "config_templates"


def test_default_project_config_templates_should_be_loadable_yaml() -> None:
    """所有默认项目配置模板都应存在、可读取且是 YAML 对象。"""

    load_default_project_config_templates.cache_clear()
    templates = load_default_project_config_templates()

    assert set(templates) == set(CONFIG_FILE_MAP)
    for config_name, file_name in CONFIG_FILE_MAP.items():
        template_path = PROJECT_CONFIG_TEMPLATE_ROOT / file_name
        parsed_value = yaml.safe_load(templates[config_name])

        assert template_path.is_file()
        assert templates[config_name] == template_path.read_text(encoding="utf-8")
        assert isinstance(parsed_value, dict)

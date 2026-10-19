"""文件功能：真实 CLI 验收的临时内存 Profile 适配，凭证仅从进程环境读取，不改用户配置。"""

import json
import os
import sys

from wp import config


def drill_config() -> config.CliConfig:
    """测试配置在导入命令前注入，后续仍通过真实 Click 命令与 HTTP Client 执行。"""
    return config.CliConfig.model_validate(json.loads(os.environ["WP_DRILL_PROFILE"]))


config.load_config = drill_config
from wp.cli import main

main(args=sys.argv[1:])

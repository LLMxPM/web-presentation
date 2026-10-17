"""文件功能：页面与组件保存链路的 AssetModel 展示参数静态校验入口。"""

from __future__ import annotations

from app.core.model_view_options import validate_model_view_options
from app.services.resource_reference_parser import ResourceReferenceParser

# 单次保存最多上报的错误条数，避免多实例源码产生超长错误详情。
_MAX_REPORTED_ERRORS = 10


def collect_model_view_option_errors(source: str) -> list[str]:
    """静态校验 Vue 源码中 AssetModel 实例的展示参数，返回有界错误列表。

    只校验可静态求值的字面量属性；动态绑定交给 Runtime 归一化兜底，
    name 的合法性由资源引用冻结链路负责，这里跳过必填检查。
    """

    payloads = ResourceReferenceParser.collect_vue_model_view_option_payloads(source)
    errors: list[str] = []
    for index, payload in enumerate(payloads, start=1):
        # 填充占位 name 以跳过必填检查；占位值永远不会进入错误信息或持久化。
        payload.setdefault("name", "-")
        for message in validate_model_view_options(payload):
            errors.append(f"AssetModel 实例 #{index}：{message}")
            if len(errors) >= _MAX_REPORTED_ERRORS:
                return errors
    return errors

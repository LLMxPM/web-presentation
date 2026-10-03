"""文件功能：验证 External 路由拒绝缺失、歧义或手工伪造的鉴权元数据。"""

import pytest
from fastapi import APIRouter, Depends

from app.api.dependencies_external import require_external_operation
from app.api.external_openapi import ExternalAPIRoute


async def _endpoint() -> dict[str, str]:
    """返回最小响应，供路由装配失败场景使用。"""

    return {"message": "测试"}


def test_external_route_without_operation_dependency_fails_assembly() -> None:
    """新外部路由缺少真实操作依赖时，不能成为无法发现或无权限声明的入口。"""

    router = APIRouter(route_class=ExternalAPIRoute)
    with pytest.raises(RuntimeError, match="缺少操作鉴权规格"):
        router.add_api_route("/new-external-operation", _endpoint)


def test_external_route_with_ambiguous_permissions_fails_assembly() -> None:
    """多个静态权限声明不能被合并成一个会误导客户端的操作。"""

    router = APIRouter(route_class=ExternalAPIRoute)
    with pytest.raises(RuntimeError, match="鉴权规格不明确"):
        router.add_api_route("/ambiguous-operation", _endpoint, dependencies=[
            Depends(require_external_operation("page.get")),
            Depends(require_external_operation("component.get")),
        ])


def test_manual_metadata_cannot_override_actual_permissions() -> None:
    """路由装饰器不能手工声称公开或减少 Scope 来覆盖真实鉴权规格。"""

    router = APIRouter(route_class=ExternalAPIRoute)
    with pytest.raises(RuntimeError, match="不能覆盖实际鉴权"):
        router.add_api_route("/forged-operation", _endpoint,
                             dependencies=[Depends(require_external_operation("page.get"))],
                             openapi_extra={"x-wp-operation": {"public": True, "required_scopes": []}})

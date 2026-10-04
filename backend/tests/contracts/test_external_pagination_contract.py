"""文件功能：约束 External 列表 URL Query 与真实分页 DTO 上下界一致，消费者不能绕过预算。"""

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.api.routes.external import v1_router
from app.schemas.common import ListQuery


def test_external_query_exports_runtime_pagination_bounds():
    """七类分页列表公开 1 起始页与 1～100 页长，仍保留各接口既有默认值。"""
    app = FastAPI()
    app.include_router(v1_router, prefix="/api")
    document = app.openapi()
    for path, default in (("/projects", 20), ("/projects/{project_id}/pages", 50), ("/components", 50),
                          ("/assets", 50), ("/themes", 50), ("/styles", 50), ("/fonts", 50)):
        parameters = {item["name"]: item["schema"] for item in document["paths"]["/api/v1" + path]["get"]["parameters"]
                      if item["in"] == "query"}
        assert parameters["page"]["minimum"] == 1 and parameters["page"]["default"] == 1
        assert parameters["page_size"]["minimum"] == 1 and parameters["page_size"]["maximum"] == 100
        assert parameters["page_size"]["default"] == default
    assert ListQuery(page=1, page_size=100).page_size == 100
    for changes in ({"page": 0}, {"page_size": 0}, {"page_size": 101}):
        with pytest.raises(ValidationError):
            ListQuery(**changes)

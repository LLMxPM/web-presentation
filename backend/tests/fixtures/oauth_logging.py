"""文件功能：为 OAuth 日志测试绑定生产请求上下文并读取结构化事件。"""

import json

from app.core.logging_config import JsonLineFormatter, bind_request_id, reset_request_id


async def call(client, request_id, method, path, **kwargs):
    """沿用生产 request ID 上下文，仅绑定日志环境；身份、路由、数据库和响应均走真实实现。"""
    context = bind_request_id(request_id)
    try:
        return await client.request(method, path, **kwargs)
    finally:
        reset_request_id(context)


def events(caplog, name):
    """用生产 formatter 读取固定日志，确保测试时上下文已恢复仍保留原请求关联。"""
    formatter = JsonLineFormatter(service="backend")
    return [
        json.loads(formatter.format(row))
        for row in caplog.records
        if getattr(row, "event", None) == name
    ]

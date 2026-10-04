"""文件功能：验证 Backend 已提交但客户端丢失 Mutation 受理响应时的幂等恢复。"""

import httpx
import pytest
from app.models.api_idempotency_record import ApiIdempotencyRecord
from app.models.api_mutation_job import ApiMutationJob
from sqlalchemy import select

from tests.fixtures.oauth_mutations import SOURCE, delegate_headers


async def test_lost_acceptance_response_can_be_recovered_with_original_key(
    oauth_mutation_client, monkeypatch
):
    """传输在 Backend 提交后丢失响应；新委托以原路径/参数/key 恢复持久受理结果。"""
    client, factory, access, _ = oauth_mutation_client
    path = "/api/v1/pages"
    payload = {"project_id": 1, "name": "页面", "source_code": SOURCE}
    original_send = client.send
    dropped = False

    async def drop_first_response(request, **kwargs):
        """保留真实 ASGI 执行和事务提交，仅模拟客户端未收到首次受理响应。"""
        nonlocal dropped
        response = await original_send(request, **kwargs)
        if request.url.path == path and not dropped:
            dropped = True
            assert response.status_code == 202
            await response.aclose()
            raise httpx.ReadError("模拟受理响应丢失", request=request)
        return response

    monkeypatch.setattr(client, "send", drop_first_response)
    headers = await delegate_headers(client, access["access_token"])
    with pytest.raises(httpx.ReadError):
        await client.post(path, json=payload, headers=headers)
    recovered = await client.post(
        path,
        json=payload,
        headers=await delegate_headers(client, access["access_token"]),
    )
    assert recovered.status_code == 202, recovered.text
    async with factory() as session:
        jobs = (await session.scalars(select(ApiMutationJob))).all()
        assert len(jobs) == 1 and jobs[0].status == "pending"
        record = await session.get(ApiIdempotencyRecord, jobs[0].idempotency_record_id)
        assert recovered.json() == record.response_body

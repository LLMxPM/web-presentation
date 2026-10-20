"""文件功能：生成主题写入指纹与仅供已完成结果重放的旧版兼容指纹。"""

from app.schemas.external_api import ExternalThemeCreateRequest, ExternalThemeUpdateRequest
from app.schemas.theme import WorkspaceThemeCreateRequest
from app.services.idempotency_service import IdempotencyService


def theme_create_fingerprints(
    path: str,
    payload: ExternalThemeCreateRequest,
    internal_payload: WorkspaceThemeCreateRequest,
) -> tuple[str, tuple[str, ...]]:
    """创建沿用默认值补全后的原始算法，同时兼容曾使用外部 DTO 的版本。"""

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST", path=path, json_data=internal_payload.model_dump(mode="json")
    )
    previous = IdempotencyService.calculate_request_fingerprint(
        http_method="POST", path=path, json_data=payload.model_dump(mode="json")
    )
    return fingerprint, (previous,)


def theme_update_fingerprints(
    path: str,
    payload: ExternalThemeUpdateRequest,
) -> tuple[str, tuple[str, ...]]:
    """更新使用版本化字段集；旧全量算法有 null 歧义时保守拒绝，不重新写入。"""

    fields = payload.model_dump(mode="json", exclude_unset=True)
    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="PATCH", path=path, json_data={"theme_patch_version": 2, "fields": fields}
    )
    previous = IdempotencyService.calculate_request_fingerprint(
        http_method="PATCH", path=path, json_data=fields
    )
    legacy = [previous]
    # 最早的全量指纹无法证明 null 是否显式提交；只为无 null 输入恢复旧结果。
    if all(value is not None for value in fields.values()):
        legacy.append(IdempotencyService.calculate_request_fingerprint(
            http_method="PATCH", path=path,
            json_data=payload.to_workspace_update().model_dump(mode="json"),
        ))
    return fingerprint, tuple(legacy)

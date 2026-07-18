"""文件功能：验证 preview artifact 专用 manifest 扩展的边界约束。"""

import pytest

from app.services.preview_service import PreviewService


def test_append_manifest_extensions_should_add_visual_edit_metadata() -> None:
    """专用预览元数据应能追加，同时保持标准字段不变。"""

    manifest: dict[str, object] = {
        "artifact_kind": "page_visual_edit_preview",
        "tenant_id": "tenant_1",
    }

    PreviewService._append_manifest_extensions(
        manifest,
        {
            "visual_edit": {
                "protocol_version": 1,
                "page_id": 12,
                "base_version_no": 3,
            }
        },
    )

    assert manifest["artifact_kind"] == "page_visual_edit_preview"
    assert manifest["visual_edit"] == {
        "protocol_version": 1,
        "page_id": 12,
        "base_version_no": 3,
    }


def test_append_manifest_extensions_should_reject_reserved_key_override() -> None:
    """扩展字段不得覆盖 artifact_kind 等标准 manifest 字段。"""

    manifest: dict[str, object] = {"artifact_kind": "preview_artifact"}

    with pytest.raises(ValueError, match="不能覆盖标准字段：artifact_kind"):
        PreviewService._append_manifest_extensions(
            manifest,
            {"artifact_kind": "page_visual_edit_preview"},
        )

"""文件功能：验证旧三维分析元数据在新增动作字段后仍可读取且不宣称动作可用。"""

from app.schemas.asset import AssetAnalysisMetadata


def test_legacy_animation_summary_defaults_to_unsupported() -> None:
    """旧记录缺少时长、签名与分析版本时，动作按未分析处理。"""

    metadata = AssetAnalysisMetadata.model_validate(
        {
            "schema_version": 1,
            "kind": "model3d",
            "model3d": {
                "format": "glb",
                "animations": [{"index": 0, "name": "OldIdle", "channel_count": 2}],
            },
        }
    )

    assert metadata.model3d is not None
    assert metadata.model3d.animation_analysis_version == 0
    animation = metadata.model3d.animations[0]
    assert animation.supported is False
    assert animation.duration_ms == 0
    assert animation.signature == ""
    assert animation.unsupported_reasons == []

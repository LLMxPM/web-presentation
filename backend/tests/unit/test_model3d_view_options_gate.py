"""文件功能：验证 AssetModel 展示参数静态校验入口的错误语义与有界输出。"""

from app.services.model3d_view_options_gate import collect_model_view_option_errors


def test_gate_should_report_static_violations_with_instance_context() -> None:
    """静态字面量违规应带实例序号上报。"""

    errors = collect_model_view_option_errors(
        """
<template>
  <AssetModel name="a" scene-index="-1" lighting="dramatic" />
</template>
        """
    )

    assert any("实例 #1" in error and "sceneIndex" in error for error in errors)
    assert any("实例 #1" in error and "lighting" in error for error in errors)


def test_gate_should_skip_dynamic_bindings_without_false_positives() -> None:
    """动态绑定的字段不应产生误报。"""

    errors = collect_model_view_option_errors(
        """
<template>
  <AssetModel :name="assetName" :scene-index="sceneIdx" :background="themeColor" />
</template>
        """
    )

    assert errors == []


def test_gate_should_report_pairing_violations_for_static_camera_group() -> None:
    """成对约束在相机组全部可静态求值时应被校验。"""

    errors = collect_model_view_option_errors(
        """
<template>
  <AssetModel name="a" :camera-position="[0, 1, 4]" :camera-fov="60" />
</template>
        """
    )

    assert any("cameraPosition 与 cameraTarget 必须成对" in error for error in errors)


def test_gate_should_bound_reported_error_count() -> None:
    """多实例多错误时上报条数应有界。"""

    instances = "\n".join(
        f'<AssetModel name="m{i}" scene-index="-1" />' for i in range(30)
    )
    errors = collect_model_view_option_errors(f"<template>{instances}</template>")

    assert 0 < len(errors) <= 10

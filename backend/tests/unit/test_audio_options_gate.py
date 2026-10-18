"""文件功能：验证 AssetAudio 播放参数与多旁白冲突的静态校验边界。"""

from app.services.audio_options_gate import collect_asset_audio_errors
from app.services.resource_reference_parser import ResourceReferenceParser


def _wrap(template: str) -> str:
    """把模板片段包装成最小可解析 Vue 源码。"""

    return f"<template>{template}</template>"


def test_asset_audio_references_should_be_collected_by_generic_asset_parser() -> None:
    """通用 Asset* name 解析应自动覆盖 AssetAudio，不新增第二套引用清单。"""

    result = ResourceReferenceParser.collect_vue_asset_references(
        _wrap('<AssetAudio name="narration-01" /><asset-audio :name="\'whoosh\'" />')
    )

    assert result.asset_names == ["narration-01", "whoosh"]
    assert result.has_dynamic is False


def test_valid_content_and_narration_props_should_pass() -> None:
    """静态字面量满足契约时不应产生错误。"""

    errors = collect_asset_audio_errors(
        _wrap(
            """
            <AssetAudio name="intro" purpose="content" controls :volume="0.8" :playback-rate="1.25" preload="auto" loop />
            <AssetAudio name="narration" purpose="narration" :controls="false" :loop="false" />
            """
        )
    )

    assert errors == []


def test_narration_loop_and_numeric_bounds_should_be_rejected() -> None:
    """旁白循环、音量/速率越界应给出有界中文错误。"""

    errors = collect_asset_audio_errors(
        _wrap(
            """
            <AssetAudio name="narration" purpose="narration" loop />
            <AssetAudio name="too-loud" :volume="1.1" />
            <AssetAudio name="too-fast" :playback-rate="2.1" />
            <AssetAudio name="too-slow" :playbackRate="0.4" />
            """
        )
    )

    joined = "\n".join(errors)
    assert "页面旁白不允许 loop=true" in joined
    assert "volume 必须是 0 到 1" in joined
    assert "playbackRate 必须是 0.5 到 2" in joined
    assert all(len(item) < 200 for item in errors)


def test_unbound_numeric_and_boolean_attributes_should_fail_strict_types() -> None:
    """组件普通属性传字符串，严格数字与布尔契约应拒绝。"""

    errors = collect_asset_audio_errors(
        _wrap('<AssetAudio name="voice" volume="0.8" controls="false" />')
    )

    joined = "\n".join(errors)
    assert "volume 必须是 0 到 1 之间的有限数字" in joined
    assert "controls 必须是布尔值" in joined


def test_unknown_purpose_and_preload_should_be_rejected() -> None:
    """enum 字段只允许契约词汇。"""

    errors = collect_asset_audio_errors(
        _wrap('<AssetAudio name="voice" purpose="background" preload="eager" />')
    )

    joined = "\n".join(errors)
    assert "purpose 只允许 content 或 narration" in joined
    assert "preload 只允许 none、metadata 或 auto" in joined


def test_dynamic_props_should_be_skipped_for_runtime_validation() -> None:
    """动态表达式无法静态判定时跳过，不误报。"""

    errors = collect_asset_audio_errors(
        _wrap(
            '<AssetAudio :name="currentName" :purpose="mode" :volume="volume" :controls="enabled" :loop="shouldLoop" />'
        )
    )

    assert errors == []


def test_multiple_static_narrations_should_be_rejected() -> None:
    """同一源码内多个静态旁白目标应阻断，避免同时说话。"""

    errors = collect_asset_audio_errors(
        _wrap(
            """
            <AssetAudio name="narration-a" purpose="narration" />
            <AssetAudio name="content" />
            <AssetAudio name="narration-b" purpose="narration" />
            """
        )
    )

    assert errors == [
        '同一源码最多只能有一个 purpose="narration" 的 AssetAudio 实例（当前 2 个）。'
    ]


def test_dynamic_narration_should_not_count_as_static_conflict() -> None:
    """动态 purpose 不参与静态多旁白计数，交给 Runtime 处理。"""

    errors = collect_asset_audio_errors(
        _wrap(
            """
            <AssetAudio name="narration-a" purpose="narration" />
            <AssetAudio name="dynamic" :purpose="mode" />
            """
        )
    )

    assert errors == []


def test_empty_name_and_comments_should_be_bound() -> None:
    """空 name 应报错，注释中的实例不应参与校验。"""

    errors = collect_asset_audio_errors(
        _wrap(
            """
            <!-- <AssetAudio name="ignored" purpose="narration" loop /> -->
            <AssetAudio name="" />
            """
        )
    )

    assert errors == ["AssetAudio 实例 #1：name 不能为空。"]

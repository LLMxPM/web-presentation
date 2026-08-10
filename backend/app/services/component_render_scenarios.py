"""文件功能：从组件 previewSchema ready payload 构造有界的默认态与 preset 渲染场景。"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass

COMPONENT_SCENARIO_LIMIT = 10


@dataclass(slots=True, frozen=True)
class ComponentRenderScenario:
    """组件浏览器诊断中的单个默认态或 preset 状态。"""

    key: str
    state: dict[str, object]


def build_component_render_scenarios(
    ready_payload: dict[str, object],
) -> tuple[list[ComponentRenderScenario], int]:
    """根据 ready 中的默认状态和 schema 构造有界场景。"""

    default_state = ready_payload.get("defaultState")
    normalized_default = deepcopy(default_state) if isinstance(default_state, dict) else {
        "props": {}, "slots": {}, "mocks": {}, "activePresetKey": None,
    }
    scenarios = [ComponentRenderScenario(key="default", state=normalized_default)]
    seen_state_hashes = {_build_state_hash(normalized_default)}
    schema = ready_payload.get("schema")
    raw_presets = schema.get("presets") if isinstance(schema, dict) else None
    presets = [item for item in raw_presets if isinstance(item, dict)] if isinstance(raw_presets, list) else []
    selected_presets = presets[:COMPONENT_SCENARIO_LIMIT]
    for index, preset in enumerate(selected_presets):
        preset_key = str(preset.get("key") or preset.get("name") or f"preset-{index + 1}")
        next_state = deepcopy(normalized_default)
        for field in ("props", "slots", "mocks"):
            base_value = next_state.get(field)
            override_value = preset.get(field)
            next_state[field] = {
                **(base_value if isinstance(base_value, dict) else {}),
                **(override_value if isinstance(override_value, dict) else {}),
            }
        next_state["activePresetKey"] = preset_key
        state_hash = _build_state_hash(next_state)
        if state_hash in seen_state_hashes:
            continue
        seen_state_hashes.add(state_hash)
        scenarios.append(ComponentRenderScenario(key=f"preset:{preset_key}", state=next_state))
    return scenarios, max(0, len(presets) - len(selected_presets))


def _build_state_hash(state: dict[str, object]) -> str:
    """按实际渲染输入去重场景，preset 标识本身不参与状态身份。"""

    return json.dumps(
        {field: state.get(field) for field in ("props", "slots", "mocks")},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

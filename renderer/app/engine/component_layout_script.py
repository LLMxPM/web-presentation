"""文件功能：组件预览布局测量与多场景诊断脚本，覆盖运行时错误、资源与几何事实。"""

from __future__ import annotations

COMPONENT_SCENARIO_LIMIT = 16


def build_component_render_layout_script() -> str:
    """返回组件 default/presets 场景诊断脚本，含 runtime/console 错误与布局测量。"""

    return r"""
async (payload) => {
  const profileKey = (payload && payload.profileKey) || 'default';
  const scenarios = (payload && payload.scenarios) || [{ key: 'default' }];
  const diagnostics = [];
  const scenarioRows = [];
  const host = document.querySelector('[data-runtime-component-preview]') || document.querySelector('#app') || document.body;
  const messages = () => Array.isArray(window.__COMPONENT_CHECK_MESSAGES__) ? window.__COMPONENT_CHECK_MESSAGES__ : [];
  const runtimeErrors = Array.isArray(window.__COMPONENT_CHECK_RUNTIME_ERRORS__)
    ? window.__COMPONENT_CHECK_RUNTIME_ERRORS__
    : (window.__COMPONENT_CHECK_RUNTIME_ERRORS__ = []);
  const consoleErrors = Array.isArray(window.__COMPONENT_CHECK_CONSOLE_ERRORS__)
    ? window.__COMPONENT_CHECK_CONSOLE_ERRORS__
    : (window.__COMPONENT_CHECK_CONSOLE_ERRORS__ = []);
  const applyScenario = window.__RENDER_APPLY_SCENARIO__;
  const timeoutMs = 15000;

  const waitMessage = async (predicate) => {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      const hit = messages().find(predicate);
      if (hit) return hit;
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    return null;
  };

  const pushDiag = (item) => {
    diagnostics.push({
      severity: item.severity || 'error',
      source: item.source || 'component-render',
      code: item.code || 'COMPONENT_RENDER_RUNTIME_ERROR',
      message: String(item.message || ''),
      scenario_key: item.scenario_key || 'default',
      profile_key: item.profile_key || profileKey,
      facts: item.facts || {},
      suggestion: item.suggestion || null,
    });
  };

  const measureLayout = () => {
    const frame = document.querySelector('.component-preview-placement__frame') || host;
    if (!(frame instanceof HTMLElement)) {
      return { available: false, reason: '组件预览 placement frame 不存在。' };
    }
    const frameRect = frame.getBoundingClientRect();
    const candidates = Array.from(frame.children).filter((node) => node instanceof Element);
    const visibleElements = candidates.filter((node) => {
      const style = window.getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      return style.display !== 'none'
        && style.visibility !== 'hidden'
        && Number(style.opacity || '1') > 0
        && rect.width > 0
        && rect.height > 0;
    });
    const rootRect = visibleElements.reduce((result, node) => {
      const rect = node.getBoundingClientRect();
      if (!result) {
        return { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom };
      }
      return {
        left: Math.min(result.left, rect.left),
        top: Math.min(result.top, rect.top),
        right: Math.max(result.right, rect.right),
        bottom: Math.max(result.bottom, rect.bottom),
      };
    }, null);
    const normalizedRootRect = rootRect
      ? {
          left: rootRect.left,
          top: rootRect.top,
          right: rootRect.right,
          bottom: rootRect.bottom,
          width: Math.max(0, rootRect.right - rootRect.left),
          height: Math.max(0, rootRect.bottom - rootRect.top),
        }
      : null;
    const intersection = normalizedRootRect
      ? {
          width: Math.max(0, Math.min(normalizedRootRect.right, frameRect.right) - Math.max(normalizedRootRect.left, frameRect.left)),
          height: Math.max(0, Math.min(normalizedRootRect.bottom, frameRect.bottom) - Math.max(normalizedRootRect.top, frameRect.top)),
        }
      : { width: 0, height: 0 };
    const clipped = Array.from(frame.querySelectorAll('*')).flatMap((node) => {
      if (!(node instanceof HTMLElement)) return [];
      const style = window.getComputedStyle(node);
      const clipsX = ['hidden', 'clip'].includes(style.overflowX) && node.scrollWidth > node.clientWidth + 2;
      const clipsY = ['hidden', 'clip'].includes(style.overflowY) && node.scrollHeight > node.clientHeight + 2;
      if (!clipsX && !clipsY) return [];
      const tag = node.tagName.toLowerCase();
      const id = node.id ? `#${node.id}` : '';
      const classes = Array.from(node.classList).slice(0, 2).map((value) => `.${value}`).join('');
      return [{
        selector_hint: `${tag}${id}${classes}`,
        clipped_x_px: clipsX ? Math.max(0, node.scrollWidth - node.clientWidth) : 0,
        clipped_y_px: clipsY ? Math.max(0, node.scrollHeight - node.clientHeight) : 0,
      }];
    }).slice(0, 10);
    const rectPayload = (rect) => ({
      left: rect.left,
      top: rect.top,
      right: rect.right,
      bottom: rect.bottom,
      width: rect.width,
      height: rect.height,
    });
    return {
      available: true,
      visible_root_count: visibleElements.length,
      frame: rectPayload(frameRect),
      root: normalizedRootRect,
      intersection_area: intersection.width * intersection.height,
      overflow: {
        horizontal_px: Math.max(0, frame.scrollWidth - frame.clientWidth),
        vertical_px: Math.max(0, frame.scrollHeight - frame.clientHeight),
      },
      clipped,
    };
  };

  const layoutDiagnosticsFrom = (layout, scenarioKey) => {
    const items = [];
    if (!layout || !layout.available) {
      items.push({
        severity: 'error',
        source: 'component-layout',
        code: 'COMPONENT_RENDER_EMPTY',
        message: String((layout && layout.reason) || '组件预览没有可测量结果。'),
        scenario_key: scenarioKey,
        profile_key: profileKey,
      });
      return items;
    }
    if (Number(layout.visible_root_count || 0) <= 0 || !layout.root) {
      items.push({
        severity: 'error',
        source: 'component-layout',
        code: 'COMPONENT_RENDER_EMPTY',
        message: `${scenarioKey} 没有可见的组件根内容。`,
        scenario_key: scenarioKey,
        profile_key: profileKey,
        facts: layout,
        suggestion: '检查根节点的条件渲染、display、visibility、opacity 和宽高。',
      });
      return items;
    }
    if (Number(layout.intersection_area || 0) <= 0) {
      items.push({
        severity: 'error',
        source: 'component-layout',
        code: 'COMPONENT_RENDER_OUTSIDE_FRAME',
        message: `${scenarioKey} 的可见内容完全位于 placement frame 外。`,
        scenario_key: scenarioKey,
        profile_key: profileKey,
        facts: layout,
        suggestion: '检查绝对定位、transform 和固定尺寸，确保组件相对宿主 frame 布局。',
      });
    }
    const overflow = layout.overflow || {};
    for (const [direction, code, label] of [
      ['horizontal_px', 'COMPONENT_RENDER_HORIZONTAL_OVERFLOW', '水平'],
      ['vertical_px', 'COMPONENT_RENDER_VERTICAL_OVERFLOW', '垂直'],
    ]) {
      const pixels = Number(overflow[direction] || 0);
      if (pixels > 2) {
        items.push({
          severity: 'warning',
          source: 'component-layout',
          code,
          message: `${scenarioKey} 在 placement frame 中${label}溢出 ${pixels.toFixed(0)}px。`,
          scenario_key: scenarioKey,
          profile_key: profileKey,
          facts: { overflow_px: pixels, frame: layout.frame, root: layout.root },
          suggestion: '检查固定宽高、padding、box-sizing 和响应式尺寸约束。',
        });
      }
    }
    if (Array.isArray(layout.clipped) && layout.clipped.length) {
      items.push({
        severity: 'warning',
        source: 'component-layout',
        code: 'COMPONENT_RENDER_CLIPPED',
        message: `${scenarioKey} 中发现 ${layout.clipped.length} 个可能被 overflow 裁切的节点。`,
        scenario_key: scenarioKey,
        profile_key: profileKey,
        facts: { nodes: layout.clipped },
        suggestion: '确认裁切是否为设计意图；若不是，调整容器尺寸或 overflow 规则。',
      });
    }
    return items;
  };

  const collectRuntimeIssues = (scenarioKey, marker) => {
    const items = [];
    const runtimeSlice = runtimeErrors.splice(0, runtimeErrors.length);
    const consoleSlice = consoleErrors.splice(0, consoleErrors.length);
    for (const message of [...new Set([...runtimeSlice, ...consoleSlice])]) {
      items.push({
        severity: 'error',
        source: 'component-render',
        code: 'COMPONENT_RENDER_RUNTIME_ERROR',
        message: String(message),
        scenario_key: scenarioKey,
        profile_key: profileKey,
        facts: { marker },
      });
    }
    return items;
  };

  // 等待组件预览 ready/error 握手。
  const bootstrap = await waitMessage((item) =>
    item.type === 'component-preview:ready' || item.type === 'component-preview:error');
  if (bootstrap && bootstrap.type === 'component-preview:error') {
    const message = (bootstrap.payload && bootstrap.payload.message) || '组件预览启动失败。';
    pushDiag({
      code: 'COMPONENT_PREVIEW_BOOTSTRAP_FAILED',
      message: String(message),
      scenario_key: 'default',
    });
    return {
      diagnostics,
      scenarios: [{ key: 'default', profile_key: profileKey, status: 'failed', diagnostic_count: 1 }],
      layout: { profile_key: profileKey, scenario_count: 1 },
    };
  }
  if (!bootstrap) {
    pushDiag({
      code: 'COMPONENT_PREVIEW_BOOTSTRAP_FAILED',
      message: '组件预览 ready 消息超时。',
      scenario_key: 'default',
    });
    return {
      diagnostics,
      scenarios: [{ key: 'default', profile_key: profileKey, status: 'failed', diagnostic_count: 1 }],
      layout: { profile_key: profileKey, scenario_count: 1 },
    };
  }

  await waitMessage((item) =>
    (item.type === 'component-preview:render-settled' && !(item.payload && item.payload.requestId))
    || item.type === 'component-preview:error');
  if (document.fonts && document.fonts.ready) {
    try { await document.fonts.ready; } catch (e) { /* 忽略字体失败 */ }
  }

  for (const scenario of scenarios) {
    const key = scenario.key || 'default';
    const state = scenario.state || null;
    const props = scenario.props || null;
    const slots = scenario.slots || null;
    const mocks = scenario.mocks || null;
    const hasOverride = Boolean(state || props || slots || mocks);
    const before = diagnostics.length;
    runtimeErrors.length = 0;
    consoleErrors.length = 0;
    try {
      if (key !== 'default' || hasOverride) {
        if (typeof applyScenario !== 'function') {
          pushDiag({
            code: 'COMPONENT_PREVIEW_BOOTSTRAP_FAILED',
            message: `组件场景 ${key} 切换能力缺失。`,
            scenario_key: key,
          });
          scenarioRows.push({ key, profile_key: profileKey, status: 'failed', diagnostic_count: 1 });
          continue;
        }
        const requestId = `scn-${key}-${Date.now()}`;
        const ack = await applyScenario({ scenarioKey: key, profileKey, requestId, state, props, slots, mocks });
        const settled = await waitMessage((item) =>
          (item.type === 'component-preview:render-settled' && item.payload && item.payload.requestId === requestId)
          || item.type === 'component-preview:error');
        if (!ack || ack.ok !== true || (settled && settled.type === 'component-preview:error')) {
          const message = (settled && settled.payload && settled.payload.message)
            || `组件场景 ${key} 切换失败。`;
          pushDiag({
            code: 'COMPONENT_PREVIEW_BOOTSTRAP_FAILED',
            message: String(message),
            scenario_key: key,
          });
          scenarioRows.push({ key, profile_key: profileKey, status: 'failed', diagnostic_count: 1 });
          continue;
        }
      }
      for (const item of collectRuntimeIssues(key, 'scenario')) {
        pushDiag(item);
      }
      const layout = measureLayout();
      for (const item of layoutDiagnosticsFrom(layout, key)) {
        pushDiag(item);
      }
      const count = diagnostics.length - before;
      scenarioRows.push({
        key,
        profile_key: profileKey,
        status: count ? 'failed' : 'passed',
        diagnostic_count: count,
      });
    } catch (error) {
      pushDiag({
        code: 'COMPONENT_PREVIEW_BOOTSTRAP_FAILED',
        message: String(error && error.message ? error.message : error),
        scenario_key: key,
      });
      scenarioRows.push({ key, profile_key: profileKey, status: 'failed', diagnostic_count: 1 });
    }
  }
  return {
    diagnostics,
    scenarios: scenarioRows,
    layout: {
      profile_key: profileKey,
      scenario_count: scenarioRows.length,
      measurement: measureLayout(),
      meta: {
        canvas_size: { width: window.innerWidth, height: window.innerHeight },
        threshold_scale: 1,
      },
    },
  };
}
"""

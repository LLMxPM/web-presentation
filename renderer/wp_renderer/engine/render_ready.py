"""文件功能：Runtime 强制就绪协议 render-ready.v1/v2 的等待与核对逻辑。"""

from __future__ import annotations

from typing import Any

from render_contracts.constants import RUNTIME_RENDER_PROTOCOL_VERSION, RUNTIME_RENDER_PROTOCOL_VERSION_V2
from render_contracts.schema import DiagnosticItem

RUNTIME_READY_PROTOCOL = RUNTIME_RENDER_PROTOCOL_VERSION


async def wait_for_render_ready(
    page: Any,
    *,
    timeout_ms: int,
    expected_artifact_id: str | None = None,
    expected_input_digest: str | None = None,
    protocol: str = RUNTIME_READY_PROTOCOL,
) -> dict[str, Any]:
    """等待宿主协议就绪；禁止用 #app 子节点、固定 sleep 或 networkidle 替代。"""

    expression = """
    async ({ timeoutMs, protocol, artifactId, inputDigest }) => {
      const started = Date.now();
      while (Date.now() - started < timeoutMs) {
        const bridge = window.__RENDER_READY__;
        if (bridge && bridge.protocol === protocol) {
          if (artifactId) {
            if (!bridge.artifactId) {
              return { ok: false, message: 'render-ready 缺少 artifactId，协议绑定不完整' };
            }
            if (bridge.artifactId !== artifactId) {
              return { ok: false, message: 'render-ready artifactId 不匹配' };
            }
          }
          // input_digest 必须双向可核对：宿主写了就必须匹配；宿主缺失视为协议未就绪。
          if (inputDigest) {
            if (!bridge.inputDigest) {
              return { ok: false, message: 'render-ready 缺少 inputDigest，协议绑定不完整' };
            }
            if (bridge.inputDigest !== inputDigest) {
              return { ok: false, message: 'render-ready inputDigest 不匹配' };
            }
          }
          if (bridge.initFailed) {
            return { ok: false, message: bridge.message || '预览初始化失败' };
          }
          if (Array.isArray(bridge.contentExceptions) && bridge.contentExceptions.length) {
            return { ok: false, message: '页面内容初始化或准备失败', contentErrors: bridge.contentExceptions.slice(0, 20) };
          }
          const fontsReady = bridge.fonts && bridge.fonts.ready;
          const visualReady = !bridge.visualAssets || bridge.visualAssets.ready !== false;
          if (bridge.mounted && fontsReady && visualReady) {
            return { ok: true, bridge };
          }
          if (bridge.mounted && bridge.visualAssets && bridge.visualAssets.timedOut) {
            return {
              ok: false,
              message: bridge.message || '视觉资源加载超时',
              bridge,
            };
          }
        }
        await new Promise((resolve) => setTimeout(resolve, 50));
      }
      // 超时时带回页面现场，区分「错误页无协议」与「挂载未完成」。
      const resources = [];
      try {
        for (const e of performance.getEntriesByType('resource') || []) {
          resources.push(e.name + '|' + (e.responseStatus || e.transferSize || 0));
        }
      } catch (e) {}
      return {
        ok: false,
        message: '等待 ' + protocol + ' 协议超时',
        url: String(location.href || ''),
        hasBridge: Boolean(window.__RENDER_READY__),
        bridge: window.__RENDER_READY__
          ? JSON.stringify(window.__RENDER_READY__).slice(0, 800)
          : null,
        bodyStart: document.body ? String(document.body.innerText || '').slice(0, 240) : null,
        htmlStart: String(document.documentElement ? document.documentElement.outerHTML || '' : '').slice(0, 600),
        scripts: Array.from(document.scripts || []).map((s) => s.src || '(inline)').slice(0, 12),
        resources: resources.slice(0, 20),
      };
    }
    """
    return await page.evaluate(
        expression,
        {
            "timeoutMs": int(timeout_ms),
            "protocol": protocol,
            "artifactId": expected_artifact_id,
            "inputDigest": expected_input_digest,
        },
    )


def content_diagnostics_from_ready(ready: dict[str, Any]) -> list[DiagnosticItem]:
    """将 Runtime 内容错误映射为诊断；保留定位且限制条数/长度，不误报基础设施不可用。"""
    raw_errors = ready.get("contentErrors")
    if not isinstance(raw_errors, list):
        return []
    diagnostics = []
    for item in raw_errors[:20]:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "RENDER_CONTENT_ERROR")[:64]
        message = str(item.get("message") or "页面内容初始化或准备失败。")[:300]
        evidence = {}
        for source, target in (("fieldPath", "field_path"), ("trackId", "track_id")):
            if item.get(source):
                evidence[target] = str(item[source])[:160]
        location = "; ".join(f"{key}={value}" for key, value in evidence.items())
        diagnostics.append(DiagnosticItem(
            severity="error", code=code,
            message=f"{message} ({location})" if location else message,
            evidence=evidence,
        ))
    return diagnostics


def normalize_runtime_route(value: str) -> str:
    """把 Runtime 路由归一化为可比较的路径，忽略查询串、哈希和末尾斜杠。"""

    path = str(value or "").split("?", 1)[0].split("#", 1)[0].strip()
    if not path:
        return ""
    if not path.startswith("/"):
        path = f"/{path}"
    if len(path) > 1:
        path = path.rstrip("/")
    return path


def validate_static_render_bridge(bridge: Any) -> str | None:
    """校验捕获页面已固定为静态执行上下文且目标路由一致；返回错误文本或 None。"""

    if not isinstance(bridge, dict):
        return "render-ready 缺少可核对的桥状态。"
    context = str(bridge.get("executionContext") or "").strip()
    if context != "capture":
        return f"Runtime 未进入捕获执行上下文（actual={context or 'missing'}）。"
    route_path = normalize_runtime_route(str(bridge.get("routePath") or ""))
    entry_path = normalize_runtime_route(str(bridge.get("entryPath") or ""))
    if not route_path:
        return "render-ready 缺少 routePath，无法确认捕获目标路由。"
    if entry_path and route_path != entry_path:
        return f"捕获目标路由不一致（routePath={route_path}, entryPath={entry_path}）。"
    return None

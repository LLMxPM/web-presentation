"""文件功能：Runtime 强制就绪协议 render-ready.v1 的等待与核对逻辑。"""

from __future__ import annotations

from typing import Any

RUNTIME_READY_PROTOCOL = "render-ready.v1"


async def wait_for_render_ready(
    page: Any,
    *,
    timeout_ms: int,
    expected_artifact_id: str | None = None,
    expected_input_digest: str | None = None,
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
      return { ok: false, message: '等待 render-ready.v1 协议超时' };
    }
    """
    return await page.evaluate(
        expression,
        {
            "timeoutMs": int(timeout_ms),
            "protocol": RUNTIME_READY_PROTOCOL,
            "artifactId": expected_artifact_id,
            "inputDigest": expected_input_digest,
        },
    )

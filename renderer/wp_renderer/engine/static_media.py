"""文件功能：在 Renderer 截图前固定捕获页面目标层，并让视频以 poster 或有界首帧静态呈现。"""

from __future__ import annotations

from typing import Any

STATIC_MEDIA_TIMEOUT_MS = 3000
MIN_STATIC_MEDIA_TIMEOUT_MS = 300

_STATIC_CAPTURE_SCRIPT = r"""
async ({ timeoutMs, expectedRoute }) => {
  const normalize = (value) => {
    let path = String(value || '').split('?')[0].split('#')[0].trim();
    if (!path) return '';
    if (!path.startsWith('/')) path = '/' + path;
    if (path.length > 1) path = path.replace(/\/+$/, '');
    return path;
  };
  const isVisible = (element) => {
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  let layers = Array.from(document.querySelectorAll('.runtime-page-print-source')).filter(isVisible);
  let routePath = layers[0]?.dataset?.runtimeRoutePath || '';
  if (layers.length === 0) {
    // 单页 module 预览由 ViewPreview 承载，没有项目路由画布；其路由一致性已由
    // render-ready 桥的 entryPath/routePath 校验，这里只确认唯一可见页面根。
    const standalone = document.querySelector('[data-runtime-view-preview-state="ready"] .runtime-view-preview-source');
    if (standalone && isVisible(standalone)) {
      layers = [standalone];
      routePath = expectedRoute || '';
    }
  }
  const layerIssue = layers.length !== 1
    ? `捕获画布应只保留一个页面层，实际 ${layers.length} 个`
    : (expectedRoute && normalize(routePath) !== normalize(expectedRoute)
      ? `捕获页面路由不一致（${routePath || 'missing'} != ${expectedRoute}）`
      : '');
  const issues = [];
  const media = Array.from(document.querySelectorAll('video, audio'));
  for (const element of media) {
    if (!element.paused) element.pause();
    if (element.hasAttribute('autoplay')) element.removeAttribute('autoplay');
  }
  const hasFrame = (video) => video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0;
  const videos = Array.from(document.querySelectorAll('video')).filter((video) => {
    if (video.getClientRects().length === 0) return false;
    return Boolean(video.currentSrc || video.src || video.querySelector('source'));
  });
  const pending = [];
  let posterVideos = 0;
  for (const video of videos) {
    const poster = String(video.getAttribute('poster') || '').trim();
    if (poster) {
      posterVideos += 1;
      // 浏览器预加载首帧后会隐藏 poster；重置到未加载资源状态以恢复静态海报。
      try {
        video.pause();
        video.removeAttribute('autoplay');
        video.preload = 'none';
        video.load();
      } catch (error) {}
      continue;
    }
    if (hasFrame(video)) continue;
    try {
      if (video.preload === 'none') video.preload = 'auto';
      if (video.readyState < 1) video.load();
    } catch (error) {}
    pending.push(video);
  }
  if (pending.length > 0) {
    await new Promise((resolve) => {
      let settled = false;
      const events = ['loadeddata', 'canplay', 'seeked', 'error'];
      const finish = () => {
        if (settled) return;
        settled = true;
        cleanup();
        resolve();
      };
      const check = () => {
        if (pending.every(hasFrame)) finish();
      };
      const timer = setTimeout(finish, Math.max(0, timeoutMs));
      const cleanup = () => {
        clearTimeout(timer);
        for (const video of pending) {
          for (const name of events) video.removeEventListener(name, check);
        }
      };
      for (const video of pending) {
        for (const name of events) video.addEventListener(name, check, { once: true });
      }
      check();
    });
  }
  for (const video of pending) {
    if (hasFrame(video)) continue;
    const src = String(video.currentSrc || video.src || '(source)');
    issues.push(video.error ? `视频加载失败：${src}` : `视频首帧在限定时间内不可用：${src}`);
  }
  // 事件回调期间页面脚本可能再次拉起媒体，截图前做最终闸门。
  for (const element of media) {
    if (!element.paused) element.pause();
  }
  return {
    ok: !layerIssue && issues.length === 0,
    layerIssue,
    routePath,
    totalMedia: media.length,
    videos: videos.length,
    posterVideos,
    frameVideos: videos.filter(hasFrame).length,
    pendingVideos: pending.length,
    issues,
  };
}
"""


async def prepare_static_capture(
    page: Any,
    *,
    expected_route: str,
    timeout_ms: int,
) -> dict[str, Any]:
    """固定页面目标层与视频首帧；超时只等待指定上限，不依赖实际播放。"""

    bounded_timeout = max(MIN_STATIC_MEDIA_TIMEOUT_MS, int(timeout_ms))
    result = await page.evaluate(
        _STATIC_CAPTURE_SCRIPT,
        {"timeoutMs": bounded_timeout, "expectedRoute": str(expected_route or "")},
    )
    return result if isinstance(result, dict) else {}


def static_capture_error(result: dict[str, Any]) -> str | None:
    """把静态捕获探针结果映射为可诊断错误；通过时返回 None。"""

    if not isinstance(result, dict) or not result:
        return "静态捕获探针返回无效结果。"
    if result.get("ok"):
        return None
    parts: list[str] = []
    layer_issue = str(result.get("layerIssue") or "").strip()
    if layer_issue:
        parts.append(layer_issue)
    for issue in result.get("issues") or []:
        text = str(issue or "").strip()
        if text:
            parts.append(text)
    return "；".join(parts[:3]) or "捕获页面未达到静态就绪条件。"

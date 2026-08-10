"""文件功能：生成组件预览浏览器端布局测量脚本，返回高置信度可见性、越界、溢出与裁切事实。"""

from __future__ import annotations


def build_component_render_layout_script() -> str:
    """返回在组件预览宿主页中执行的布局测量脚本。"""

    return r"""
    () => {
      const frame = document.querySelector('.component-preview-placement__frame');
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
        if (!(node instanceof HTMLElement)) {
          return [];
        }
        const style = window.getComputedStyle(node);
        const clipsX = ['hidden', 'clip'].includes(style.overflowX) && node.scrollWidth > node.clientWidth + 2;
        const clipsY = ['hidden', 'clip'].includes(style.overflowY) && node.scrollHeight > node.clientHeight + 2;
        if (!clipsX && !clipsY) {
          return [];
        }
        return [{
          selector_hint: buildSelectorHint(node),
          clipped_x_px: clipsX ? Math.max(0, node.scrollWidth - node.clientWidth) : 0,
          clipped_y_px: clipsY ? Math.max(0, node.scrollHeight - node.clientHeight) : 0,
        }];
      }).slice(0, 10);

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

      function rectPayload(rect) {
        return {
          left: rect.left,
          top: rect.top,
          right: rect.right,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height,
        };
      }

      function buildSelectorHint(node) {
        const tag = node.tagName.toLowerCase();
        const id = node.id ? `#${node.id}` : '';
        const classes = Array.from(node.classList).slice(0, 2).map((value) => `.${value}`).join('');
        return `${tag}${id}${classes}`;
      }
    }
    """

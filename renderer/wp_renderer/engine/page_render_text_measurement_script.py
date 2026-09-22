"""文件功能：生成文本无换行宽度测量的浏览器端辅助函数。"""

from __future__ import annotations


def build_text_measurement_helpers() -> str:
    """构造锁定原始元素宽度的测量函数，避免 flex/grid 自动尺寸导致误判。"""

    return r"""
      const measureNoWrapOverflow = (element) => {
        const originalClientWidth = element.clientWidth;
        const originalOffsetWidth = element.offsetWidth;
        if (originalClientWidth <= 0 || originalOffsetWidth <= 0) {
          return 0;
        }

        const previousStyleAttribute = element.getAttribute('style');
        const lockedWidth = `${originalOffsetWidth}px`;

        try {
          element.style.setProperty('white-space', 'nowrap', 'important');
          element.style.setProperty('box-sizing', 'border-box', 'important');
          element.style.setProperty('inline-size', lockedWidth, 'important');
          element.style.setProperty('width', lockedWidth, 'important');
          element.style.setProperty('min-inline-size', lockedWidth, 'important');
          element.style.setProperty('max-inline-size', lockedWidth, 'important');
          element.style.setProperty('min-width', lockedWidth, 'important');
          element.style.setProperty('max-width', lockedWidth, 'important');
          element.style.setProperty('flex', '0 0 auto', 'important');
          return Math.max(0, element.scrollWidth - originalClientWidth);
        } finally {
          if (previousStyleAttribute === null) {
            element.removeAttribute('style');
          } else {
            element.setAttribute('style', previousStyleAttribute);
          }
        }
      };
    """

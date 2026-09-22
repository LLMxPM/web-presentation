"""文件功能：生成页面视觉检测共用的元素定位、表面识别和几何辅助函数。"""

from __future__ import annotations


def build_spatial_analysis_shared_helpers() -> str:
    """构造视觉检测共用函数，统一目标引用、设计意图和几何计算。"""

    return r"""
      const spatialExcludedTags = new Set([
        'SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'META', 'LINK',
        'PATH', 'G', 'DEFS', 'CLIPPATH', 'MASK'
      ]);
      const spatialInteractiveSelector = [
        'a[href]', 'button', 'input', 'select', 'textarea',
        '[role="button"]', '[role="link"]', '[tabindex]'
      ].join(',');

      const parseCssLength = (value) => {
        const parsed = Number.parseFloat(value);
        return Number.isFinite(parsed) ? parsed : 0;
      };

      const hasDirectText = (element) => (
        Array.from(element.childNodes).some(node => (
          node.nodeType === Node.TEXT_NODE && String(node.nodeValue || '').trim()
        ))
      );

      const classifySpatialContent = (element) => {
        const style = window.getComputedStyle(element);
        if (element.matches(spatialInteractiveSelector)) {
          return 'interactive';
        }
        if (['IMG', 'SVG', 'CANVAS', 'VIDEO', 'PICTURE'].includes(element.tagName)) {
          return 'image';
        }
        const text = String(element.textContent || '').replace(/\s+/g, ' ').trim();
        if (
          element.getAttribute('aria-hidden') === 'true'
          || (!text && style.pointerEvents === 'none')
        ) {
          return 'decorative';
        }
        return hasDirectText(element) ? 'text' : 'container';
      };

      const parseBackgroundAlpha = (value) => {
        const normalized = String(value || '').trim().toLowerCase();
        if (!normalized || normalized === 'transparent') {
          return 0;
        }
        const slashMatch = normalized.match(/\/\s*([\d.]+)(%)?\s*\)$/);
        if (slashMatch) {
          const alpha = Number.parseFloat(slashMatch[1]);
          return slashMatch[2] ? alpha / 100 : alpha;
        }
        const rgbaMatch = normalized.match(/^rgba\([^,]+,[^,]+,[^,]+,\s*([\d.]+)\s*\)$/);
        return rgbaMatch ? Number.parseFloat(rgbaMatch[1]) : 1;
      };

      const describeSurface = (element) => {
        const style = window.getComputedStyle(element);
        const backgroundAlpha = Math.max(0, Math.min(1, parseBackgroundAlpha(style.backgroundColor)));
        const backgroundImage = style.backgroundImage && style.backgroundImage !== 'none';
        const hasBorder = [
          ['borderTopWidth', 'borderTopStyle'],
          ['borderRightWidth', 'borderRightStyle'],
          ['borderBottomWidth', 'borderBottomStyle'],
          ['borderLeftWidth', 'borderLeftStyle']
        ].some(([width, borderStyle]) => (
          parseCssLength(style[width]) > 0 && !['none', 'hidden'].includes(style[borderStyle])
        ));
        const hasShadow = Boolean(style.boxShadow && style.boxShadow !== 'none');
        let kind = 'none';
        if (backgroundImage) {
          kind = /gradient\(/i.test(style.backgroundImage) ? 'gradient' : 'image';
        } else if (backgroundAlpha >= 0.05) {
          kind = 'solid';
        } else if (hasBorder) {
          kind = 'border';
        }
        return {
          painted: backgroundImage || backgroundAlpha >= 0.05 || hasBorder,
          kind,
          background_alpha: Math.round(backgroundAlpha * 1000) / 1000,
          has_border: hasBorder,
          has_shadow: hasShadow
        };
      };

      const isSpatialCandidate = (element) => {
        if (
          element === root
          || spatialExcludedTags.has(element.tagName)
          || (element.closest('svg') && element.tagName !== 'SVG')
          || !isVisible(element)
        ) {
          return false;
        }
        const rect = element.getBoundingClientRect();
        return rect.width > 0.5 && rect.height > 0.5;
      };

      const isOverflowCandidate = (element) => {
        if (!isSpatialCandidate(element)) {
          return false;
        }
        const style = window.getComputedStyle(element);
        return (
          classifySpatialContent(element) !== 'container'
          || describeSurface(element).painted
          || element.children.length === 0
          || style.position === 'absolute'
          || style.position === 'fixed'
        );
      };

      const getElementScale = (element) => {
        const rect = element.getBoundingClientRect();
        return {
          x: element.offsetWidth > 0 ? rect.width / element.offsetWidth : 1,
          y: element.offsetHeight > 0 ? rect.height / element.offsetHeight : 1
        };
      };

      const getPaddingRect = (element) => {
        const rect = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);
        const scale = getElementScale(element);
        return {
          left: rect.left + parseCssLength(style.borderLeftWidth) * scale.x,
          right: rect.right - parseCssLength(style.borderRightWidth) * scale.x,
          top: rect.top + parseCssLength(style.borderTopWidth) * scale.y,
          bottom: rect.bottom - parseCssLength(style.borderBottomWidth) * scale.y
        };
      };

      const intersectSpatialRects = (first, second) => {
        const left = Math.max(first.left, second.left);
        const right = Math.min(first.right, second.right);
        const top = Math.max(first.top, second.top);
        const bottom = Math.min(first.bottom, second.bottom);
        return {
          left,
          right,
          top,
          bottom,
          width: Math.max(0, right - left),
          height: Math.max(0, bottom - top)
        };
      };

      const calculateVisibleRatio = (rect, clipRect) => {
        const area = Math.max(0, rect.width * rect.height);
        if (area <= 0) {
          return 0;
        }
        const intersection = intersectSpatialRects(rect, clipRect);
        return Math.round((intersection.width * intersection.height / area) * 1000) / 1000;
      };

      const buildSpatialIntentSignals = (element) => {
        const style = window.getComputedStyle(element);
        const signals = [];
        if (style.position === 'absolute' || style.position === 'fixed') {
          signals.push('absolute_position');
        }
        if (style.transform && style.transform !== 'none') {
          signals.push('transform');
        }
        if (
          parseCssLength(style.marginLeft) < 0
          || parseCssLength(style.marginRight) < 0
          || parseCssLength(style.marginTop) < 0
          || parseCssLength(style.marginBottom) < 0
        ) {
          signals.push('negative_margin');
        }
        if (style.zIndex !== 'auto') {
          signals.push('explicit_z_index');
        }
        if (style.pointerEvents === 'none') {
          signals.push('pointer_events_none');
        }
        if (element.getAttribute('aria-hidden') === 'true') {
          signals.push('aria_hidden');
        }
        if (style.mixBlendMode !== 'normal') {
          signals.push('blend_mode');
        }
        return signals;
      };

      const resolveIntentLikelihood = (signals) => {
        const strongSignals = new Set([
          'absolute_position', 'transform', 'negative_margin', 'grid_layering'
        ]);
        if (signals.some(signal => strongSignals.has(signal))) {
          return 'likely';
        }
        return signals.length ? 'possible' : 'unlikely';
      };

      const resolveGeometryReliability = (element) => {
        const style = window.getComputedStyle(element);
        if (style.clipPath && style.clipPath !== 'none') {
          return 'approximate';
        }
        const match = String(style.transform || '').match(/^matrix\(([^)]+)\)$/);
        if (match) {
          const values = match[1].split(',').map(Number);
          if (Math.abs(values[1] || 0) > 0.001 || Math.abs(values[2] || 0) > 0.001) {
            return 'approximate';
          }
        }
        return 'reliable';
      };

      const buildDomPath = (element) => {
        if (element === root) {
          return ':scope';
        }
        const segments = [];
        let current = element;
        while (current && current !== root) {
          const tag = String(current.tagName || '').toLowerCase();
          const sameTagSiblings = current.parentElement
            ? Array.from(current.parentElement.children).filter(sibling => sibling.tagName === current.tagName)
            : [current];
          const index = Math.max(1, sameTagSiblings.indexOf(current) + 1);
          segments.unshift(`${tag}:nth-of-type(${index})`);
          current = current.parentElement;
        }
        return `:scope > ${segments.join(' > ')}`;
      };

      const buildElementLocator = (element) => {
        const visualNodeId = String(element.getAttribute('data-page-visual-node-id') || '').trim();
        if (visualNodeId) {
          return {
            kind: 'visual_node_id',
            value: `[data-page-visual-node-id=${JSON.stringify(visualNodeId)}]`
          };
        }
        if (element.id && root.querySelectorAll(`#${CSS.escape(element.id)}`).length === 1) {
          return { kind: 'id', value: `#${CSS.escape(element.id)}` };
        }
        return { kind: 'dom_path', value: buildDomPath(element) };
      };

      const resolveRepeatIndex = (element) => {
        if (!element.parentElement) {
          return null;
        }
        const classes = typeof element.className === 'string'
          ? element.className.trim().split(/\s+/).filter(Boolean).sort().join(' ')
          : '';
        const matches = Array.from(element.parentElement.children).filter(sibling => {
          const siblingClasses = typeof sibling.className === 'string'
            ? sibling.className.trim().split(/\s+/).filter(Boolean).sort().join(' ')
            : '';
          return sibling.tagName === element.tagName && siblingClasses === classes;
        });
        return matches.length > 1 ? matches.indexOf(element) + 1 : null;
      };

      const buildTargetLabel = (element) => {
        const tag = String(element.tagName || '').toLowerCase();
        const id = element.id ? `#${element.id}` : '';
        const classes = typeof element.className === 'string'
          ? element.className.trim().split(/\s+/).filter(Boolean).slice(0, 4).join('.')
          : '';
        return `${tag}${id}${classes ? `.${classes}` : ''}`;
      };

      const describeCompactTarget = (element) => {
        const text = String(element.textContent || '').replace(/\s+/g, ' ').trim();
        return {
          label: buildTargetLabel(element),
          locator: buildElementLocator(element),
          text_sample: text.slice(0, 100),
          repeat_index: resolveRepeatIndex(element)
        };
      };

      const describeLayoutTarget = (element) => {
        const text = String(element.textContent || '').replace(/\s+/g, ' ').trim();
        const classTokens = typeof element.className === 'string'
          ? element.className.trim().split(/\s+/).filter(Boolean).slice(0, 6)
          : [];
        return {
          label: buildTargetLabel(element),
          locator: buildElementLocator(element),
          code_hint: {
            tag: String(element.tagName || '').toLowerCase(),
            class_tokens: classTokens,
            text_sample: text.slice(0, 100),
            repeat_index: resolveRepeatIndex(element)
          },
          content_kind: classifySpatialContent(element),
          surface: describeSurface(element),
          geometry_reliability: resolveGeometryReliability(element)
        };
      };
    """

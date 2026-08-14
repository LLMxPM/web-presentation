"""文件功能：生成页面真实渲染视觉检测脚本，返回版本化文本、分排、越界和空间关系。"""

from __future__ import annotations

from app.services.page_render_layout_summary_script import build_layout_summary_helpers
from app.services.page_render_overflow_analysis_script import build_overflow_analysis_helpers
from app.services.page_render_overlap_analysis_script import build_overlap_analysis_helpers
from app.services.page_render_spatial_shared_script import build_spatial_analysis_shared_helpers
from app.services.page_render_text_measurement_script import build_text_measurement_helpers
from app.services.page_render_wrapped_items_script import build_wrapped_item_analysis_helpers
from app.services.page_render_empty_area_script import build_empty_area_analysis_helpers


def build_page_render_layout_script() -> str:
    """构造浏览器端布局分析脚本，返回诊断与 v2 视觉检测契约。"""

    script = r"""
    () => {
      const maxTextLength = 300;
      const resultLimits = {
        text_layouts: 50,
        item_groups: 20,
        overflows: 30,
        spatial_relations: 30,
        empty_regions: 10
      };
      const root = document.querySelector('.runtime-page-print-source, .runtime-view-preview-source');
      const emptyAnalysis = {
        schema_version: 3,
        meta: null,
        summary: {
          attention: 'none',
          message: '未发现需要关注的视觉检测结果。',
          totals: {
            text_layouts: 0,
            item_groups: 0,
            overflows: 0,
            spatial_relations: 0,
            empty_regions: 0
          },
          returned: {
            text_layouts: 0,
            item_groups: 0,
            overflows: 0,
            spatial_relations: 0,
            empty_regions: 0
          },
          truncated: false
        },
        text_layouts: [],
        item_groups: [],
        overflows: [],
        spatial_relations: [],
        empty_regions: []
      };
      if (!root) {
        return {
          diagnostics: [{
            severity: 'warning',
            source: 'runtime-render',
            code: 'PAGE_RENDER_DIAGNOSTICS_UNAVAILABLE',
            message: '未找到页面渲染根节点 .runtime-page-print-source 或 .runtime-view-preview-source，无法分析布局。'
          }],
          layout_analysis: emptyAnalysis
        };
      }

      const rootRect = root.getBoundingClientRect();
      // 画布短边作为全部固定像素阈值的折算基准：默认 1920x1080 画布行为保持不变，
      // 小画布（如 1000x560 图卡）阈值随尺寸收紧，大画布（如 4K）阈值线性放宽。
      const canvasBase = Math.min(rootRect.width, rootRect.height);
      const scaleCanvasPx = (px) => Math.max(px * 0.5, canvasBase * (px / 1080));
      const tolerancePx = Math.max(1, canvasBase / 540);
      // 裁剪画布上 scrollHeight 会包含绝对定位装饰层的溢出，无法区分装饰与真实内容，
      // 因此只使用逐元素 rect 判定；可滚动或可见溢出画布仍以 scrollHeight 差值兜底。
      const rootStyle = window.getComputedStyle(root);
      const rootClipsOverflow = (
        ['hidden', 'clip'].includes(rootStyle.overflowX)
        && ['hidden', 'clip'].includes(rootStyle.overflowY)
      );
      const rootScrollOverflow = rootClipsOverflow
        ? 0
        : Math.max(0, Math.ceil(root.scrollHeight - root.clientHeight - tolerancePx));
      let maxVisualOverflow = 0;
      const offenders = [];

      const isVisible = (element) => {
        const style = window.getComputedStyle(element);
        if (
          style.display === 'none'
          || style.visibility === 'hidden'
          || Number(style.opacity) === 0
        ) {
          return false;
        }
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      };

      const describeElement = (element) => {
        const visualNodeId = String(element.getAttribute('data-page-visual-node-id') || '').trim();
        if (visualNodeId) {
          return `[data-page-visual-node-id="${visualNodeId}"]`;
        }
        const tagName = String(element.tagName || '').toLowerCase();
        const id = element.id ? `#${element.id}` : '';
        const className = typeof element.className === 'string'
          ? element.className.trim().split(/\s+/).filter(Boolean).slice(0, 4).join('.')
          : '';
        return `${tagName}${id}${className ? `.${className}` : ''}`;
      };

      const describeOverflowElement = (element, overflowPx) => {
        const text = String(element.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60);
        return `${describeElement(element)} 超出 ${overflowPx}px${text ? `，文本：${text}` : ''}`;
      };

__WRAPPED_ITEM_ANALYSIS_HELPERS__
__SPATIAL_ANALYSIS_SHARED_HELPERS__
__OVERFLOW_ANALYSIS_HELPERS__
__OVERLAP_ANALYSIS_HELPERS__
__TEXT_MEASUREMENT_HELPERS__
__EMPTY_AREA_ANALYSIS_HELPERS__
__LAYOUT_SUMMARY_HELPERS__

      const skipDecorOverflow = (element) => {
        const kind = classifySpatialContent(element);
        if (kind === 'decorative') {
          return true;
        }
        const style = window.getComputedStyle(element);
        if (
          (kind === 'container' || kind === 'image')
          && (style.position === 'absolute' || style.position === 'fixed')
        ) {
          return true;
        }
        return false;
      };

      for (const element of root.querySelectorAll('*')) {
        if (!isVisible(element) || !isOverflowCandidate(element)) {
          continue;
        }
        if (skipDecorOverflow(element)) {
          continue;
        }
        const rect = element.getBoundingClientRect();
        const overflowPx = Math.ceil(rect.bottom - rootRect.bottom - tolerancePx);
        if (overflowPx <= 0) {
          continue;
        }
        maxVisualOverflow = Math.max(maxVisualOverflow, overflowPx);
        offenders.push({ element, overflowPx });
      }

      const diagnostics = [];
      const overflowPx = Math.max(rootScrollOverflow, maxVisualOverflow);
      if (overflowPx > 0) {
        const samples = offenders
          .sort((left, right) => right.overflowPx - left.overflowPx)
          .slice(0, 3)
          .map(item => describeOverflowElement(item.element, item.overflowPx));
        const sampleText = samples.length ? ` 疑似元素：${samples.join('；')}` : '';
        diagnostics.push({
          severity: 'warning',
          source: 'runtime-render',
          code: 'PAGE_RENDER_BOTTOM_OVERFLOW',
          message: `页面内容底部超出画布 ${overflowPx}px，预览或导出时可能被裁切。${sampleText}`
        });
      }

      const blockDisplays = new Set([
        'block', 'flex', 'grid', 'flow-root', 'list-item', 'table-cell',
        'table-caption', 'inline-block', 'inline-flex', 'inline-grid'
      ]);
      const excludedTags = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'SVG', 'CANVAS']);
      const textGroups = new Map();
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);

      const findTextOwner = (textNode) => {
        let element = textNode.parentElement;
        while (element && element !== root) {
          if (excludedTags.has(element.tagName) || !isVisible(element)) {
            return null;
          }
          if (blockDisplays.has(window.getComputedStyle(element).display)) {
            return element;
          }
          element = element.parentElement;
        }
        return element === root ? root : null;
      };

      let currentNode = walker.nextNode();
      while (currentNode) {
        if (String(currentNode.nodeValue || '').trim()) {
          const owner = findTextOwner(currentNode);
          if (owner) {
            const nodes = textGroups.get(owner) || [];
            nodes.push(currentNode);
            textGroups.set(owner, nodes);
          }
        }
        currentNode = walker.nextNode();
      }

      const segmentGraphemes = (value) => {
        if (typeof Intl !== 'undefined' && typeof Intl.Segmenter === 'function') {
          return Array.from(new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(value), item => item.segment);
        }
        return Array.from(value);
      };

      const appendTextReason = (result, code, message) => {
        result.codes.push(code);
        result.messages.push(message);
      };

      const buildTextReasons = (lines, element) => {
        const result = { codes: [], messages: [] };
        const style = window.getComputedStyle(element);
        const elementRect = element.getBoundingClientRect();
        const fontSize = Number.parseFloat(style.fontSize) || 0;
        const containerWidth = elementRect.width;
        const centerAligned = style.textAlign === 'center';
        const lastLine = String(lines.at(-1) || '').trim();
        const previousLine = String(lines.at(-2) || '').trim();
        const meaningful = segmentGraphemes(lastLine.replace(/[\s，。！？；：、,.!?;:'"“”‘’（）()[\]【】《》<>—–-]/g, ''));
        const containsCjk = /[\u3400-\u9fff]/u.test(lastLine);
        // 孤行判定按容器宽度与字号折算：最后一行实际占宽约 55% 以上或达到标题级字号才报告，
        // 避免宽容器内短句、窄容器内 1-2 字结尾被机械判为孤行。
        const estimatedWidth = meaningful.length * fontSize * (containsCjk ? 1 : 0.6);
        const shortLinePlausible = (
          containerWidth <= 0
          || estimatedWidth >= containerWidth * 0.55
          || fontSize >= 18
        );
        if (
          containsCjk
          && meaningful.length > 0
          && meaningful.length <= 2
          && shortLinePlausible
        ) {
          appendTextReason(
            result,
            'short_last_line',
            `最后一行仅包含 ${meaningful.length} 个有效汉字，可能形成孤行${centerAligned ? '（居中文本，标题或签名设计可忽略）' : ''}`
          );
        }
        const englishWords = lastLine.match(/[A-Za-z]+(?:['’-][A-Za-z]+)*/g) || [];
        if (!containsCjk && englishWords.length === 1 && lines.length > 1 && shortLinePlausible) {
          appendTextReason(
            result,
            'single_word_last_line',
            `英文最后一行仅包含一个单词，可能形成孤词${centerAligned ? '（居中文本，标题或签名设计可忽略）' : ''}`
          );
        }
        if (/^[，。！？；：、,.!?;:）)\]】》]/u.test(lastLine)) {
          appendTextReason(result, 'leading_punctuation', '最后一行以不适合行首的标点开头');
        }
        if (lastLine && !/[\p{L}\p{N}]/u.test(lastLine)) {
          appendTextReason(result, 'punctuation_only_line', '最后一行仅包含标点或符号');
        }
        if (
          /\d(?:\.\d+)?$/u.test(previousLine)
          && /^(?:亿元|万元|°C|℃|‰|%|元|万|亿|kg|km|cm|mm|g|m)/iu.test(lastLine)
        ) {
          appendTextReason(
            result,
            'split_number_unit',
            '数字与单位可能被拆分到两行'
          );
        }
        return result;
      };

      const measureTextGroup = (element, textNodes) => {
        const style = window.getComputedStyle(element);
        const elementRect = element.getBoundingClientRect();
        const scale = element.offsetWidth > 0 ? elementRect.width / element.offsetWidth : 1;
        const fontSize = Number.parseFloat(style.fontSize) || 0;
        const lineTolerance = Math.max(1, fontSize * Math.max(scale, 0.01) * 0.2);
        const lines = [];
        let preservedNewlineCount = 0;

        const resolveLine = (top) => {
          let line = lines.find(item => Math.abs(item.top - top) <= lineTolerance);
          if (!line) {
            line = { top, left: Number.POSITIVE_INFINITY, text: '' };
            lines.push(line);
          }
          return line;
        };

        for (const textNode of textNodes) {
          const value = String(textNode.nodeValue || '');
          preservedNewlineCount += (value.match(/\n/g) || []).length;
          let offset = 0;
          for (const grapheme of segmentGraphemes(value)) {
            const nextOffset = offset + grapheme.length;
            const range = document.createRange();
            range.setStart(textNode, offset);
            range.setEnd(textNode, nextOffset);
            const rects = Array.from(range.getClientRects()).filter(rect => rect.width > 0 || rect.height > 0);
            range.detach();
            if (rects.length) {
              const rect = rects[0];
              const line = resolveLine(rect.top);
              line.left = Math.min(line.left, rect.left);
              line.text += grapheme;
            } else if (lines.length && /\s/u.test(grapheme)) {
              lines[lines.length - 1].text += grapheme;
            }
            offset = nextOffset;
          }
        }

        lines.sort((left, right) => left.top - right.top || left.left - right.left);
        const lineTexts = lines.map(line => line.text.replace(/\s+/g, ' ').trim()).filter(Boolean);
        if (lineTexts.length <= 1) {
          return null;
        }

        const explicitBreakCount = element.querySelectorAll('br').length + preservedNewlineCount;
        const breakKind = explicitBreakCount === 0
          ? 'soft'
          : explicitBreakCount >= lineTexts.length - 1 ? 'explicit' : 'mixed';
        const nowrapOverflowPx = measureNoWrapOverflow(element);
        const normalizedText = textNodes
          .map(textNode => String(textNode.nodeValue || ''))
          .join('')
          .replace(/\s+/g, ' ')
          .trim();
        const stability = breakKind === 'soft' && nowrapOverflowPx <= tolerancePx
          ? 'boundary'
          : 'stable';
        const textReasons = stability === 'boundary'
          ? {
              codes: ['boundary_wrap'],
              messages: [
                `逐字行位检测为 ${lineTexts.length} 行，但强制单行仅净超宽 ${nowrapOverflowPx}px；这是兼容性临界结果，不应视为确定换行`
              ]
            }
          : buildTextReasons(lineTexts, element);
        const result = {
          target: describeCompactTarget(element),
          text: normalizedText.slice(0, maxTextLength),
          line_count: lineTexts.length,
          first_line: lineTexts[0].slice(0, maxTextLength),
          last_line: lineTexts.at(-1).slice(0, maxTextLength),
          break_kind: breakKind,
          stability,
          attention: textReasons.codes.length ? 'review' : 'none',
          reason_codes: textReasons.codes
        };
        if (normalizedText.length > maxTextLength) {
          result.text_truncated = true;
        }
        if (stability === 'boundary') {
          result.font_size_px = Math.round(fontSize * 100) / 100;
          result.container_width_px = Math.round(elementRect.width * 100) / 100;
          result.nowrap_overflow_px = nowrapOverflowPx;
        }
        if (textReasons.messages.length) {
          result.message = `${textReasons.messages.join('；')}。`;
        }
        return result;
      };

      const textLayouts = [];
      for (const [element, textNodes] of textGroups.entries()) {
        const measurement = measureTextGroup(element, textNodes);
        if (measurement) {
          textLayouts.push(measurement);
        }
      }
      const itemGroups = analyzeWrappedItemGroups();
      const overflows = analyzeSpatialOverflows();
      const spatialRelations = analyzeSpatialRelations();
      const emptyRegions = analyzeEmptyRegions();
      const allResults = {
        text_layouts: prioritizeLayoutResults(textLayouts),
        item_groups: prioritizeLayoutResults(itemGroups),
        overflows: prioritizeLayoutResults(overflows),
        spatial_relations: prioritizeLayoutResults(spatialRelations),
        empty_regions: prioritizeLayoutResults(emptyRegions)
      };
      const returnedResults = Object.fromEntries(
        Object.entries(allResults).map(([key, items]) => [
          key,
          items.slice(0, resultLimits[key])
        ])
      );

      return {
        diagnostics,
        layout_analysis: {
          schema_version: 3,
          meta: {
            canvas_size: {
              width: Math.round(rootRect.width * 100) / 100,
              height: Math.round(rootRect.height * 100) / 100
            },
            threshold_scale: Math.round(canvasBase * 100) / 100
          },
          summary: buildLayoutSummary(allResults, returnedResults),
          ...returnedResults
        }
      };
    }
    """
    replacements = {
        "__WRAPPED_ITEM_ANALYSIS_HELPERS__": build_wrapped_item_analysis_helpers(),
        "__SPATIAL_ANALYSIS_SHARED_HELPERS__": build_spatial_analysis_shared_helpers(),
        "__OVERFLOW_ANALYSIS_HELPERS__": build_overflow_analysis_helpers(),
        "__OVERLAP_ANALYSIS_HELPERS__": build_overlap_analysis_helpers(),
        "__TEXT_MEASUREMENT_HELPERS__": build_text_measurement_helpers(),
        "__EMPTY_AREA_ANALYSIS_HELPERS__": build_empty_area_analysis_helpers(),
        "__LAYOUT_SUMMARY_HELPERS__": build_layout_summary_helpers(),
    }
    for placeholder, value in replacements.items():
        script = script.replace(placeholder, value)
    return script

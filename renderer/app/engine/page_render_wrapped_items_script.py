"""文件功能：生成可换行直属子元素组的浏览器端布局分析脚本。"""

from __future__ import annotations


def build_wrapped_item_analysis_helpers() -> str:
    """构造 flex-wrap 子元素分排检测函数，输出统一关注级别与紧凑提示。"""

    return r"""
      const analyzeWrappedItemGroups = () => {
        const maxRowsPerGroup = 12;
        const maxItemsPerRow = 12;

        const parseLength = (value) => {
          const parsed = Number.parseFloat(value);
          return Number.isFinite(parsed) ? parsed : 0;
        };

        const isPillLike = (element) => {
          const style = window.getComputedStyle(element);
          const height = element.clientHeight;
          if (height <= 0) {
            return false;
          }
          const radii = [
            style.borderTopLeftRadius,
            style.borderTopRightRadius,
            style.borderBottomRightRadius,
            style.borderBottomLeftRadius
          ].map(parseLength);
          const minimumRadius = Math.min(...radii);
          const horizontalPadding = parseLength(style.paddingLeft) + parseLength(style.paddingRight);
          return (
            minimumRadius >= height * 0.4
            && horizontalPadding >= 8
            && element.clientWidth >= height * 1.2
          );
        };

        const groupItemsIntoRows = (items, scale) => {
          const rows = [];
          const sortedItems = [...items].sort(
            (left, right) => left.rect.top - right.rect.top || left.rect.left - right.rect.left
          );
          for (const item of sortedItems) {
            const tolerance = Math.max(1, Math.min(item.rect.height * 0.2, 6 * scale));
            let row = rows.find(candidate => (
              item.rect.top <= candidate.bottom - tolerance
              && item.rect.bottom >= candidate.top + tolerance
            ));
            if (!row) {
              row = { top: item.rect.top, bottom: item.rect.bottom, items: [] };
              rows.push(row);
            }
            row.top = Math.min(row.top, item.rect.top);
            row.bottom = Math.max(row.bottom, item.rect.bottom);
            row.items.push(item);
          }
          rows.sort((left, right) => left.top - right.top);
          for (const row of rows) {
            row.items.sort((left, right) => left.rect.left - right.rect.left);
          }
          return rows;
        };

        const resolveWrapMargin = (element, rows, scale, style) => {
          if (
            style.flexDirection !== 'row'
            || !['normal', 'start', 'flex-start'].includes(style.justifyContent)
            || rows.length <= 1
          ) {
            return null;
          }
          const containerRect = element.getBoundingClientRect();
          const contentRight = containerRect.right - (
            parseLength(style.borderRightWidth) + parseLength(style.paddingRight)
          ) * scale;
          const columnGap = parseLength(style.columnGap) * scale;
          let minimumMargin = Number.POSITIVE_INFINITY;
          for (let index = 1; index < rows.length; index += 1) {
            const previousItem = rows[index - 1].items.at(-1);
            const wrappedItem = rows[index].items[0];
            if (!previousItem || !wrappedItem) {
              continue;
            }
            const previousStyle = window.getComputedStyle(previousItem.element);
            const wrappedStyle = window.getComputedStyle(wrappedItem.element);
            const previousMarginRight = parseLength(previousStyle.marginRight) * scale;
            const wrappedMargins = (
              parseLength(wrappedStyle.marginLeft) + parseLength(wrappedStyle.marginRight)
            ) * scale;
            const available = contentRight - previousItem.rect.right - previousMarginRight;
            const required = columnGap + wrappedMargins + wrappedItem.rect.width;
            minimumMargin = Math.min(minimumMargin, Math.max(0, (required - available) / scale));
          }
          return Number.isFinite(minimumMargin)
            ? Math.round(minimumMargin * 100) / 100
            : null;
        };

        const groups = [];
        for (const element of [root, ...root.querySelectorAll('*')]) {
          if (!isVisible(element)) {
            continue;
          }
          const style = window.getComputedStyle(element);
          if (
            !['flex', 'inline-flex'].includes(style.display)
            || style.flexWrap === 'nowrap'
            || !['row', 'row-reverse'].includes(style.flexDirection)
          ) {
            continue;
          }
          const children = Array.from(element.children)
            .filter(child => {
              if (!isVisible(child)) {
                return false;
              }
              const childStyle = window.getComputedStyle(child);
              return childStyle.position !== 'absolute' && childStyle.position !== 'fixed';
            })
            .map(child => ({ element: child, rect: child.getBoundingClientRect() }));
          if (children.length < 2) {
            continue;
          }

          const elementRect = element.getBoundingClientRect();
          const scale = Math.max(
            element.offsetWidth > 0 ? elementRect.width / element.offsetWidth : 1,
            0.01
          );
          const rows = groupItemsIntoRows(children, scale);
          if (rows.length <= 1) {
            continue;
          }

          const lastRowCount = rows.at(-1).items.length;
          const previousRowCount = rows.at(-2).items.length;
          const wrapMarginPx = resolveWrapMargin(element, rows, scale, style);
          const stability = wrapMarginPx !== null && wrapMarginPx <= tolerancePx
            ? 'boundary'
            : 'stable';
          const reasonCodes = [];
          const messages = [];
          if (lastRowCount === 1 && previousRowCount > 1) {
            reasonCodes.push('single_item_last_row');
            messages.push('最后一排仅包含 1 个元素，可能形成视觉孤项');
          }
          if (stability === 'boundary') {
            reasonCodes.push('boundary_item_wrap');
            messages.push(`当前元素组距离少换一排仅约 ${wrapMarginPx}px，存在兼容性临界分排`);
          }

          const pillCount = children.filter(item => isPillLike(item.element)).length;
          const patternConfidence = Math.round((pillCount / children.length) * 100) / 100;
          groups.push({
            target: describeCompactTarget(element),
            layout: 'flex',
            item_count: children.length,
            row_count: rows.length,
            rows: rows.slice(0, maxRowsPerGroup).map((row, index) => ({
              row: index + 1,
              item_count: row.items.length,
              items: row.items.slice(0, maxItemsPerRow).map(item => (
                describeCompactTarget(item.element)
              ))
            })),
            rows_truncated: (
              rows.length > maxRowsPerGroup
              || rows.some(row => row.items.length > maxItemsPerRow)
            ),
            last_row_count: lastRowCount,
            item_pattern: patternConfidence >= 0.7 ? 'pill_like' : 'generic',
            pattern_confidence: patternConfidence,
            wrap_margin_px: wrapMarginPx,
            stability,
            attention: reasonCodes.length ? 'review' : 'none',
            reason_codes: reasonCodes,
            message: messages.length ? `${messages.join('；')}。` : null
          });
        }
        return groups;
      };
    """

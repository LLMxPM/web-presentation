"""文件功能：生成页面画布边界和中间容器越界的统一检测脚本。"""

from __future__ import annotations


def build_overflow_analysis_helpers() -> str:
    """构造统一越界事实，区分实际裁切、滚动和可见溢出。"""

    return r"""
      const analyzeSpatialOverflows = () => {
        const clipValues = new Set(['hidden', 'clip', 'auto', 'scroll']);
        const scrollValues = new Set(['auto', 'scroll']);
        const containerDisplays = new Set([
          'block', 'flex', 'grid', 'flow-root', 'list-item',
          'table-cell', 'inline-block', 'inline-flex', 'inline-grid'
        ]);

        const measureDirections = (rect, boundary) => {
          const values = {
            left: boundary.left - rect.left,
            right: rect.right - boundary.right,
            top: boundary.top - rect.top,
            bottom: rect.bottom - boundary.bottom
          };
          const overflow = {};
          for (const [direction, value] of Object.entries(values)) {
            if (value > tolerancePx) {
              overflow[direction] = Math.round(value * 100) / 100;
            }
          }
          return overflow;
        };

        const findRelevantContainerOverflow = (element, rect) => {
          let parent = element.parentElement;
          let fallback = null;
          while (parent && parent !== root) {
            const style = window.getComputedStyle(parent);
            const isLayoutContainer = (
              containerDisplays.has(style.display)
              || style.overflowX !== 'visible'
              || style.overflowY !== 'visible'
            );
            if (isLayoutContainer) {
              const directions = measureDirections(rect, getPaddingRect(parent));
              if (Object.keys(directions).length) {
                const horizontal = 'left' in directions || 'right' in directions;
                const vertical = 'top' in directions || 'bottom' in directions;
                const actuallyClipped = (
                  (horizontal && clipValues.has(style.overflowX))
                  || (vertical && clipValues.has(style.overflowY))
                );
                const candidate = { container: parent, style, directions, actuallyClipped };
                if (actuallyClipped) {
                  return candidate;
                }
                fallback ??= candidate;
              }
            }
            parent = parent.parentElement;
          }
          return fallback;
        };

        const describeLargestOverflow = (directions) => {
          const labels = { left: '左侧', right: '右侧', top: '顶部', bottom: '底部' };
          const [direction, amount] = Object.entries(directions)
            .sort((left, right) => right[1] - left[1])[0];
          return { label: labels[direction], amount };
        };

        const buildOverflowAssessment = ({
          scope,
          contentKind,
          directions,
          clipping,
          visibleRatio,
          intentSignals
        }) => {
          const largest = describeLargestOverflow(directions);
          const reasonCodes = [];
          let attention = 'none';
          let message = null;
          if (scope === 'canvas') {
            reasonCodes.push(
              ['text', 'interactive'].includes(contentKind)
                ? 'content_outside_canvas'
                : 'element_outside_canvas'
            );
            attention = ['text', 'interactive'].includes(contentKind)
              ? 'likely_issue'
              : intentSignals.length ? 'review' : 'likely_issue';
            message = `${largest.label}超出页面画布 ${largest.amount}px，预览或导出时可能不可见。`;
          } else if (clipping === 'hidden') {
            if (contentKind === 'text') {
              reasonCodes.push('text_clipped');
            } else if (contentKind === 'interactive') {
              reasonCodes.push('interactive_clipped');
            } else {
              reasonCodes.push('element_clipped');
            }
            if (visibleRatio < 0.5) {
              reasonCodes.push('mostly_clipped');
            }
            attention = ['text', 'interactive'].includes(contentKind)
              ? 'likely_issue'
              : 'review';
            message = `${largest.label}超出裁切容器 ${largest.amount}px，部分内容可能不可见。`;
          } else if (clipping === 'scrollable') {
            reasonCodes.push('scrollable_overflow');
          } else {
            reasonCodes.push('visible_overflow');
            attention = ['text', 'interactive'].includes(contentKind) ? 'review' : 'none';
            message = attention === 'review'
              ? `${largest.label}超出当前容器 ${largest.amount}px；容器允许可见溢出，请结合设计判断。`
              : null;
          }
          return { attention, reasonCodes, message };
        };

        const overflows = [];
        const rootBoundary = getPaddingRect(root);
        const candidates = Array.from(root.querySelectorAll('*')).filter(isOverflowCandidate);
        for (const element of candidates) {
          const rect = element.getBoundingClientRect();
          const target = describeLayoutTarget(element);
          const intentSignals = buildSpatialIntentSignals(element);
          const canvasDirections = measureDirections(rect, rootBoundary);
          if (Object.keys(canvasDirections).length) {
            const assessment = buildOverflowAssessment({
              scope: 'canvas',
              contentKind: target.content_kind,
              directions: canvasDirections,
              clipping: 'none',
              visibleRatio: calculateVisibleRatio(rect, rootBoundary),
              intentSignals
            });
            overflows.push({
              scope: 'canvas',
              target,
              container: null,
              directions: Object.keys(canvasDirections),
              overflow_px: canvasDirections,
              visible_ratio: calculateVisibleRatio(rect, rootBoundary),
              clipping: 'none',
              intent: {
                likelihood: resolveIntentLikelihood(intentSignals),
                signals: intentSignals
              },
              attention: assessment.attention,
              reason_codes: assessment.reasonCodes,
              message: assessment.message
            });
          }

          const containerOverflow = findRelevantContainerOverflow(element, rect);
          if (!containerOverflow) {
            continue;
          }
          const { container, style, directions, actuallyClipped } = containerOverflow;
          const horizontal = 'left' in directions || 'right' in directions;
          const vertical = 'top' in directions || 'bottom' in directions;
          const scrollable = (
            (horizontal && scrollValues.has(style.overflowX))
            || (vertical && scrollValues.has(style.overflowY))
          );
          const clipping = scrollable ? 'scrollable' : actuallyClipped ? 'hidden' : 'none';
          const visibleRatio = calculateVisibleRatio(rect, getPaddingRect(container));
          const assessment = buildOverflowAssessment({
            scope: 'container',
            contentKind: target.content_kind,
            directions,
            clipping,
            visibleRatio,
            intentSignals
          });
          overflows.push({
            scope: 'container',
            target,
            container: describeLayoutTarget(container),
            directions: Object.keys(directions),
            overflow_px: directions,
            visible_ratio: visibleRatio,
            clipping,
            intent: {
              likelihood: resolveIntentLikelihood(intentSignals),
              signals: intentSignals
            },
            attention: assessment.attention,
            reason_codes: assessment.reasonCodes,
            message: assessment.message
          });
        }
        return overflows;
      };
    """

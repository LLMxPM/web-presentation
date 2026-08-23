"""文件功能：生成页面画布与容器内部空白带的浏览器端检测脚本。"""

from __future__ import annotations


def build_empty_area_analysis_helpers() -> str:
    """构造内容带合并、纵向空隙、容器顶部/底部空白带与画布尾随空白检测函数。"""

    return r"""
      const analyzeEmptyRegions = () => {
        const maxRawRegions = 20;

        const horizontalOverlap = (first, second) => (
          Math.max(0, Math.min(first.right, second.right) - Math.max(first.left, second.left))
        );

        const isContentElement = (element) => {
          if (!isSpatialCandidate(element)) {
            return false;
          }
          const kind = classifySpatialContent(element);
          const surface = describeSurface(element);
          return kind !== 'container' || surface.painted;
        };

        const contentRects = [];
        for (const element of root.querySelectorAll('*')) {
          if (!isContentElement(element)) {
            continue;
          }
          const rect = intersectSpatialRects(
            element.getBoundingClientRect(),
            getPaddingRect(root)
          );
          if (rect.width <= tolerancePx || rect.height <= tolerancePx) {
            continue;
          }
          contentRects.push({
            element,
            rect,
            target: describeCompactTarget(element),
            kind: classifySpatialContent(element),
            surface: describeSurface(element)
          });
        }

        const rootBoundary = getPaddingRect(root);
        const rootHeight = Math.max(1, rootBoundary.bottom - rootBoundary.top);
        const sortedByTop = [...contentRects].sort(
          (left, right) => left.rect.top - right.rect.top || left.rect.left - right.rect.left
        );

        const regions = [];
        const seenGapTops = new Set();
        for (let index = 1; index < sortedByTop.length; index += 1) {
          const upper = sortedByTop[index - 1];
          const lower = sortedByTop[index];
          const gapTop = Math.min(upper.rect.bottom, lower.rect.top);
          const gapBottom = Math.max(upper.rect.bottom, lower.rect.top);
          const gapHeight = gapBottom - gapTop;
          if (gapHeight <= tolerancePx || upper.rect.bottom > lower.rect.top - tolerancePx) {
            continue;
          }
          const overlapWidth = horizontalOverlap(upper.rect, lower.rect);
          const minimumOverlap = Math.max(
            40,
            Math.min(upper.rect.width, lower.rect.width) * 0.5
          );
          if (overlapWidth < minimumOverlap) {
            continue;
          }
          const relativeThreshold = Math.max(
            scaleCanvasPx(72),
            Math.min(upper.rect.height, lower.rect.height) * 0.5,
            rootHeight * 0.1
          );
          if (gapHeight < relativeThreshold) {
            continue;
          }
          const roundedTop = Math.round(gapTop / 4);
          if (seenGapTops.has(roundedTop)) {
            continue;
          }
          seenGapTops.add(roundedTop);
          const ratio = Math.round((gapHeight / rootHeight) * 1000) / 1000;
          regions.push({
            kind: 'vertical_gap',
            first: upper.target,
            second: lower.target,
            gap_top_px: Math.round(gapTop * 100) / 100,
            gap_bottom_px: Math.round(gapBottom * 100) / 100,
            height_px: Math.round(gapHeight * 100) / 100,
            width_px: Math.round(overlapWidth * 100) / 100,
            ratio_of_canvas: ratio,
            attention: 'review',
            reason_codes: ['large_vertical_gap'],
            message: `两个内容带之间约有 ${Math.round(gapHeight)}px 纵向空白（占画布高度 ${Math.round(ratio * 100)}%）；若为封面或章节页的刻意留白可忽略。`
          });
          if (regions.length >= maxRawRegions) {
            break;
          }
        }

        const rootWidth = Math.max(1, rootBoundary.right - rootBoundary.left);
        const seenGapLefts = new Set();
        const sortedByLeft = [...contentRects].sort(
          (left, right) => left.rect.left - right.rect.left || left.rect.top - right.rect.top
        );
        for (let index = 1; index < sortedByLeft.length; index += 1) {
          const leftBlock = sortedByLeft[index - 1];
          const rightBlock = sortedByLeft[index];
          const gapLeft = Math.min(leftBlock.rect.right, rightBlock.rect.left);
          const gapRight = Math.max(leftBlock.rect.right, rightBlock.rect.left);
          const gapWidth = gapRight - gapLeft;
          if (gapWidth <= tolerancePx || leftBlock.rect.right > rightBlock.rect.left - tolerancePx) {
            continue;
          }
          const overlapHeight = Math.max(
            0,
            Math.min(leftBlock.rect.bottom, rightBlock.rect.bottom)
              - Math.max(leftBlock.rect.top, rightBlock.rect.top)
          );
          const minimumOverlap = Math.max(
            40,
            Math.min(leftBlock.rect.height, rightBlock.rect.height) * 0.5
          );
          if (overlapHeight < minimumOverlap) {
            continue;
          }
          const relativeThreshold = Math.max(
            scaleCanvasPx(72),
            Math.min(leftBlock.rect.width, rightBlock.rect.width) * 0.5,
            rootWidth * 0.1
          );
          if (gapWidth < relativeThreshold) {
            continue;
          }
          const roundedLeft = Math.round(gapLeft / 4);
          if (seenGapLefts.has(roundedLeft)) {
            continue;
          }
          seenGapLefts.add(roundedLeft);
          const ratio = Math.round((gapWidth / rootWidth) * 1000) / 1000;
          regions.push({
            kind: 'horizontal_gap',
            first: leftBlock.target,
            second: rightBlock.target,
            gap_left_px: Math.round(gapLeft * 100) / 100,
            gap_right_px: Math.round(gapRight * 100) / 100,
            width_px: Math.round(gapWidth * 100) / 100,
            height_px: Math.round(overlapHeight * 100) / 100,
            ratio_of_canvas: ratio,
            attention: 'review',
            reason_codes: ['large_horizontal_gap'],
            message: `两个内容列之间约有 ${Math.round(gapWidth)}px 横向空白（占画布宽度 ${Math.round(ratio * 100)}%）；若为分栏设计的刻意留白可忽略。`
          });
          if (regions.length >= maxRawRegions) {
            break;
          }
        }

        const seenBandKeys = new Set();
        const appendBand = (band, dedupe = true) => {
          if (regions.length >= maxRawRegions) {
            return;
          }
          if (dedupe) {
            const bandStart = band.gap_left_px ?? band.gap_top_px;
            const bandEnd = band.gap_right_px ?? band.gap_bottom_px;
            const key = [
              band.kind,
              Math.round(bandStart / 4),
              Math.round(bandEnd / 4)
            ].join(':');
            if (seenBandKeys.has(key)) {
              return;
            }
            seenBandKeys.add(key);
          }
          regions.push(band);
        };

        const analyzeParentBands = (parentElement, isRoot) => {
          if (regions.length >= maxRawRegions) {
            return;
          }
          const parentRect = getPaddingRect(parentElement);
          const parentHeight = Math.max(1, parentRect.bottom - parentRect.top);
          const style = window.getComputedStyle(parentElement);
          if (style.backgroundImage && style.backgroundImage !== 'none') {
            return;
          }
          const threshold = Math.max(
            isRoot ? scaleCanvasPx(96) : scaleCanvasPx(48),
            parentHeight * 0.15
          );
          const candidates = [];
          if (isRoot) {
            for (const item of contentRects) {
              candidates.push(item);
            }
          } else {
            for (const element of parentElement.querySelectorAll('*')) {
              if (!isContentElement(element)) {
                continue;
              }
              const rect = intersectSpatialRects(
                element.getBoundingClientRect(),
                parentRect
              );
              if (rect.width <= tolerancePx || rect.height <= tolerancePx) {
                continue;
              }
              candidates.push({
                element,
                rect,
                target: describeCompactTarget(element),
                kind: classifySpatialContent(element),
                surface: describeSurface(element)
              });
            }
          }
          if (!candidates.length) {
            return;
          }
          candidates.sort(
            (left, right) => left.rect.top - right.rect.top || left.rect.left - right.rect.left
          );
          const first = candidates[0];
          const last = candidates.reduce(
            (current, item) => item.rect.bottom > current.rect.bottom ? item : current
          );
          const parentTarget = describeCompactTarget(parentElement);
          const scopeLabel = isRoot ? '画布' : '容器';
          const leading = first.rect.top - parentRect.top;
          if (leading > threshold) {
            const ratio = Math.round((leading / parentHeight) * 1000) / 1000;
            appendBand({
              kind: 'leading_gap',
              first: first.target,
              parent: parentTarget,
              gap_top_px: Math.round(parentRect.top * 100) / 100,
              gap_bottom_px: Math.round(first.rect.top * 100) / 100,
              height_px: Math.round(leading * 100) / 100,
              ratio_of_parent: ratio,
              attention: 'review',
              reason_codes: ['leading_gap'],
              message: `${scopeLabel}顶部存在约 ${Math.round(leading)}px 空白带（占${scopeLabel}高度 ${Math.round(ratio * 100)}%），大范围 margin/padding 可能使内容整体下移；若为刻意留白可忽略。`
            });
          }
          const trailing = parentRect.bottom - last.rect.bottom;
          if (trailing > threshold) {
            const ratio = Math.round((trailing / parentHeight) * 1000) / 1000;
            const contentHeight = Math.max(0, last.rect.bottom - first.rect.top);
            const contentRatio = Math.round((contentHeight / parentHeight) * 1000) / 1000;
            const layoutContainer = style.display.includes('flex') || style.display.includes('grid');
            const nearTopThreshold = Math.max(scaleCanvasPx(48), parentHeight * 0.08);
            const sparseTopAligned = (
              !isRoot
              && layoutContainer
              && leading <= nearTopThreshold
              && contentRatio <= 0.62
              && trailing >= Math.max(scaleCanvasPx(96), parentHeight * 0.25)
            );
            const trailingReasonCodes = isRoot
              ? ['trailing_bottom_gap']
              : sparseTopAligned
                ? ['sparse_top_aligned', 'trailing_gap']
                : ['trailing_gap'];
            appendBand({
              kind: isRoot ? 'trailing_bottom_gap' : 'trailing_gap',
              first: last.target,
              parent: parentTarget,
              gap_top_px: Math.round(last.rect.bottom * 100) / 100,
              gap_bottom_px: Math.round(parentRect.bottom * 100) / 100,
              height_px: Math.round(trailing * 100) / 100,
              ratio_of_parent: ratio,
              top_gap_px: Math.round(leading * 100) / 100,
              bottom_gap_px: Math.round(trailing * 100) / 100,
              content_height_px: Math.round(contentHeight * 100) / 100,
              content_ratio_of_parent: contentRatio,
              attention: sparseTopAligned ? 'likely_issue' : 'review',
              reason_codes: trailingReasonCodes,
              message: sparseTopAligned
                ? `${scopeLabel}内容整体靠顶部排列，底部约有 ${Math.round(trailing)}px 空白（占${scopeLabel}高度 ${Math.round(ratio * 100)}%）；若非刻意的顶部版式，优先使用 justify-center、place-items-center 或调整容器高度，避免仅用 flex-1/固定高度撑开区域。`
                : isRoot
                ? `内容在画布底部上方约 ${Math.round(trailing)}px 处结束（占画布高度 ${Math.round(ratio * 100)}%）；可补充内容或调整布局。`
                : `${scopeLabel}底部存在约 ${Math.round(trailing)}px 空白带（占${scopeLabel}高度 ${Math.round(ratio * 100)}%），固定高度容器内内容可能未填满；可调整 margin/padding 或容器高度。`
            });
          }

          if (!isRoot) {
            const interiorThreshold = Math.max(scaleCanvasPx(72), parentHeight * 0.1);
            const parentDistributed = (
              style.display.includes('flex')
              && ['space-between', 'space-around', 'space-evenly', 'center'].includes(style.justifyContent)
            );
            const seenInteriorTops = new Set();
            for (let index = 1; index < candidates.length; index += 1) {
              const upper = candidates[index - 1];
              const lower = candidates[index];
              const gapTop = upper.rect.bottom;
              const gapBottom = lower.rect.top;
              const gapHeight = gapBottom - gapTop;
              if (gapHeight <= tolerancePx || upper.rect.bottom > lower.rect.top - tolerancePx) {
                continue;
              }
              const overlapWidth = horizontalOverlap(upper.rect, lower.rect);
              const minimumOverlap = Math.max(
                40,
                Math.min(upper.rect.width, lower.rect.width) * 0.5
              );
              if (overlapWidth < minimumOverlap) {
                continue;
              }
              if (gapHeight < interiorThreshold) {
                continue;
              }
              const roundedTop = Math.round(gapTop / 4);
              if (seenInteriorTops.has(roundedTop)) {
                continue;
              }
              seenInteriorTops.add(roundedTop);
              const ratio = Math.round((gapHeight / parentHeight) * 1000) / 1000;
              const hasAutoTopMargin = (() => {
                let current = lower.element;
                while (current && current !== parentElement) {
                  const classTokens = typeof current.className === 'string'
                    ? current.className.split(/\s+/)
                    : [];
                  if (
                    current.style.marginTop === 'auto'
                    || classTokens.includes('mt-auto')
                  ) {
                    return true;
                  }
                  current = current.parentElement;
                }
                return false;
              })();
              const sparseTopAligned = (
                !parentDistributed
                && style.display.includes('flex')
                && style.flexDirection === 'column'
                && hasAutoTopMargin
                && ratio >= 0.22
              );
              appendBand({
                kind: 'interior_gap',
                first: upper.target,
                second: lower.target,
                parent: parentTarget,
                gap_top_px: Math.round(gapTop * 100) / 100,
                gap_bottom_px: Math.round(gapBottom * 100) / 100,
                height_px: Math.round(gapHeight * 100) / 100,
                width_px: Math.round(overlapWidth * 100) / 100,
                ratio_of_parent: ratio,
                attention: sparseTopAligned ? 'likely_issue' : 'review',
                reason_codes: sparseTopAligned
                  ? ['sparse_top_aligned', 'interior_gap']
                  : ['interior_gap'],
                message: sparseTopAligned
                  ? `${scopeLabel}内主体内容靠顶部排列，后续内容与前一内容块之间约有 ${Math.round(gapHeight)}px 空白（占${scopeLabel}高度 ${Math.round(ratio * 100)}%）；检测到自动上边距或固定高度可能使内容脱节，优先将完整内容组垂直居中或取消 mt-auto。`
                  : parentDistributed
                  ? `${scopeLabel}内两个内容块之间约有 ${Math.round(gapHeight)}px 纵向空白（占${scopeLabel}高度 ${Math.round(ratio * 100)}%），由 ${style.justifyContent} 分布撑开；若为刻意留白可忽略。`
                  : `${scopeLabel}内两个内容块之间约有 ${Math.round(gapHeight)}px 纵向空白（占${scopeLabel}高度 ${Math.round(ratio * 100)}%），mt-auto、margin 或固定高度可能使内容脱节；若为刻意留白可忽略。`
              }, false);
              if (regions.length >= maxRawRegions) {
                break;
              }
            }
          }

          const leftmost = candidates.reduce(
            (current, item) => item.rect.left < current.rect.left ? item : current
          );
          const rightmost = candidates.reduce(
            (current, item) => item.rect.right > current.rect.right ? item : current
          );
          const parentWidth = Math.max(1, parentRect.right - parentRect.left);
          const widthThreshold = Math.max(isRoot ? 96 : 48, parentWidth * 0.15);
          const leftGap = leftmost.rect.left - parentRect.left;
          const rightGap = parentRect.right - rightmost.rect.right;
          const leftOver = leftGap > widthThreshold;
          const rightOver = rightGap > widthThreshold;
          if (leftOver || rightOver) {
            const symmetric = (
              leftOver
              && rightOver
              && Math.abs(leftGap - rightGap) <= Math.max(4, canvasBase * 0.005)
            );
            if (symmetric) {
              const ratio = Math.round((leftGap / parentWidth) * 1000) / 1000;
              appendBand({
                kind: 'left_gap',
                first: leftmost.target,
                parent: parentTarget,
                gap_left_px: Math.round(parentRect.left * 100) / 100,
                gap_right_px: Math.round(leftmost.rect.left * 100) / 100,
                width_px: Math.round(leftGap * 100) / 100,
                ratio_of_parent: ratio,
                attention: 'review',
                reason_codes: ['left_gap'],
                message: `${scopeLabel}左右两侧各存在约 ${Math.round(leftGap)}px 对称留白（占${scopeLabel}宽度 ${Math.round(ratio * 100)}%），呈居中布局；若为刻意居中留白可忽略。`
              });
            } else {
              if (leftOver) {
                const ratio = Math.round((leftGap / parentWidth) * 1000) / 1000;
                appendBand({
                  kind: 'left_gap',
                  first: leftmost.target,
                  parent: parentTarget,
                  gap_left_px: Math.round(parentRect.left * 100) / 100,
                  gap_right_px: Math.round(leftmost.rect.left * 100) / 100,
                  width_px: Math.round(leftGap * 100) / 100,
                  ratio_of_parent: ratio,
                  attention: 'review',
                  reason_codes: ['left_gap'],
                  message: `${scopeLabel}左侧存在约 ${Math.round(leftGap)}px 空白带（占${scopeLabel}宽度 ${Math.round(ratio * 100)}%），右侧留白约 ${Math.round(rightGap)}px；若为居中或刻意留白可忽略。`
                });
              }
              if (rightOver) {
                const ratio = Math.round((rightGap / parentWidth) * 1000) / 1000;
                appendBand({
                  kind: 'right_gap',
                  first: rightmost.target,
                  parent: parentTarget,
                  gap_left_px: Math.round(rightmost.rect.right * 100) / 100,
                  gap_right_px: Math.round(parentRect.right * 100) / 100,
                  width_px: Math.round(rightGap * 100) / 100,
                  ratio_of_parent: ratio,
                  attention: 'review',
                  reason_codes: ['right_gap'],
                  message: `${scopeLabel}右侧存在约 ${Math.round(rightGap)}px 空白带（占${scopeLabel}宽度 ${Math.round(ratio * 100)}%），左侧留白约 ${Math.round(leftGap)}px；若为居中或刻意留白可忽略。`
                });
              }
            }
          }
        };

        const parentElements = Array.from(root.querySelectorAll('*'))
          .filter(isSpatialCandidate)
          .reverse();
        for (const element of parentElements) {
          analyzeParentBands(element, false);
        }
        analyzeParentBands(root, true);

        return regions;
      };
    """

"""文件功能：生成元素与视觉容器重叠、贴边和临界间距检测脚本。"""

from __future__ import annotations


def build_overlap_analysis_helpers() -> str:
    """构造统一空间关系，合并元素重叠和非透明容器邻接事实。"""

    return r"""
      const analyzeSpatialRelations = () => {
        const maxRawRelations = 200;
        const attentionRank = { none: 0, review: 1, likely_issue: 2 };
        const relationRank = { overlap: 0, touching: 1, tight: 2 };

        const resolveGridLayering = (parent, first, second) => {
          const parentStyle = window.getComputedStyle(parent);
          if (!['grid', 'inline-grid'].includes(parentStyle.display)) {
            return false;
          }
          const firstArea = window.getComputedStyle(first).gridArea;
          const secondArea = window.getComputedStyle(second).gridArea;
          return firstArea !== 'auto / auto / auto / auto' && firstArea === secondArea;
        };

        const isGroupedContact = (parent, first, second) => {
          const role = String(parent.getAttribute('role') || '').toLowerCase();
          if (
            ['TABLE', 'TR', 'UL', 'OL'].includes(parent.tagName)
            || ['table', 'row', 'tablist', 'group'].includes(role)
          ) {
            return true;
          }
          const parentStyle = window.getComputedStyle(parent);
          const firstTarget = describeLayoutTarget(first);
          const secondTarget = describeLayoutTarget(second);
          const bothInteractive = (
            firstTarget.content_kind === 'interactive'
            && secondTarget.content_kind === 'interactive'
          );
          if (bothInteractive && describeSurface(parent).painted) {
            return true;
          }
          const sameBackground = (
            window.getComputedStyle(first).backgroundColor
            === window.getComputedStyle(second).backgroundColor
          );
          return (
            ['hidden', 'clip'].includes(parentStyle.overflow)
            && describeSurface(parent).painted
            && sameBackground
            && !firstTarget.surface.has_shadow
            && !secondTarget.surface.has_shadow
          );
        };

        const resolveVisualPair = (first, second) => {
          if (first.surface.painted && second.surface.painted) {
            return 'surface_surface';
          }
          if (first.surface.painted || second.surface.painted) {
            return 'surface_content';
          }
          if (
            ['text', 'interactive'].includes(first.content_kind)
            && ['text', 'interactive'].includes(second.content_kind)
          ) {
            return 'content_content';
          }
          return 'generic';
        };

        const resolveRelationGeometry = (firstRect, secondRect, bothPainted) => {
          const intersection = intersectSpatialRects(firstRect, secondRect);
          if (intersection.width > 0 && intersection.height > 0) {
            const firstArea = Math.max(1, firstRect.width * firstRect.height);
            const secondArea = Math.max(1, secondRect.width * secondRect.height);
            const intersectionArea = intersection.width * intersection.height;
            return {
              relation: 'overlap',
              axis: 'both',
              distance: -Math.min(intersection.width, intersection.height),
              metrics: {
                intersection_width_px: intersection.width,
                intersection_height_px: intersection.height,
                first_overlap_ratio: intersectionArea / firstArea,
                second_overlap_ratio: intersectionArea / secondArea,
                shared_edge_px: 0
              }
            };
          }
          if (!bothPainted) {
            return null;
          }

          const verticalShared = Math.max(
            0,
            Math.min(firstRect.bottom, secondRect.bottom) - Math.max(firstRect.top, secondRect.top)
          );
          const horizontalShared = Math.max(
            0,
            Math.min(firstRect.right, secondRect.right) - Math.max(firstRect.left, secondRect.left)
          );
          const horizontalGap = Math.max(
            secondRect.left - firstRect.right,
            firstRect.left - secondRect.right
          );
          const verticalGap = Math.max(
            secondRect.top - firstRect.bottom,
            firstRect.top - secondRect.bottom
          );
          const horizontalThreshold = Math.max(
            8,
            Math.min(firstRect.height, secondRect.height) * 0.25
          );
          const verticalThreshold = Math.max(
            8,
            Math.min(firstRect.width, secondRect.width) * 0.25
          );
          const candidates = [];
          if (
            horizontalGap >= 0
            && horizontalGap <= tolerancePx
            && verticalShared >= horizontalThreshold
          ) {
            candidates.push({
              axis: 'horizontal',
              gap: horizontalGap,
              sharedEdge: verticalShared
            });
          }
          if (
            verticalGap >= 0
            && verticalGap <= tolerancePx
            && horizontalShared >= verticalThreshold
          ) {
            candidates.push({
              axis: 'vertical',
              gap: verticalGap,
              sharedEdge: horizontalShared
            });
          }
          if (!candidates.length) {
            return null;
          }
          const closest = candidates.sort((left, right) => left.gap - right.gap)[0];
          return {
            relation: closest.gap <= 0.5 ? 'touching' : 'tight',
            axis: closest.axis,
            distance: closest.gap,
            metrics: {
              intersection_width_px: 0,
              intersection_height_px: 0,
              first_overlap_ratio: 0,
              second_overlap_ratio: 0,
              shared_edge_px: closest.sharedEdge
            }
          };
        };

        const assessRelation = ({ relation, visualPair, first, second, intent }) => {
          if (relation !== 'overlap') {
            return {
              attention: 'review',
              reasonCodes: [
                relation === 'touching'
                  ? 'independent_surfaces_touching'
                  : 'independent_surfaces_tight'
              ],
              message: relation === 'touching'
                ? '两个独立视觉容器贴边；若非组合布局，建议增加间距。'
                : '两个独立视觉容器间距不超过 2px；若非紧凑组合布局，建议增加余量。'
            };
          }

          const reasonCodes = [];
          let baseMessage = '两个元素发生视觉重叠';
          const hasInteractive = (
            first.content_kind === 'interactive'
            || second.content_kind === 'interactive'
          );
          const bothText = first.content_kind === 'text' && second.content_kind === 'text';
          if (hasInteractive) {
            reasonCodes.push('interactive_overlap');
            baseMessage = '重叠区域涉及交互元素，可能影响识别或操作';
          } else if (bothText) {
            reasonCodes.push('text_text_overlap');
            baseMessage = '两个文本元素发生视觉重叠，可能互相遮挡';
          } else if (visualPair === 'surface_surface') {
            reasonCodes.push('painted_surface_overlap');
            baseMessage = '两个独立视觉容器发生重叠';
          } else if (visualPair === 'surface_content') {
            reasonCodes.push('surface_content_overlap');
            baseMessage = '视觉容器与其他内容发生重叠';
          } else {
            reasonCodes.push('element_overlap');
          }
          if (intent.likelihood === 'unlikely') {
            reasonCodes.push('no_overlap_intent_signal');
          }
          return {
            attention: intent.likelihood === 'likely' ? 'review' : 'likely_issue',
            reasonCodes,
            message: intent.likelihood === 'likely'
              ? `${baseMessage}；检测到定位或叠层信号，请先确认是否为有意设计。`
              : `${baseMessage}；未发现明显叠层设计信号。`
          };
        };

        const relationsByPair = new Map();
        for (const parent of [root, ...root.querySelectorAll('*')]) {
          if (!isVisible(parent)) {
            continue;
          }
          const children = Array.from(parent.children)
            .filter(isSpatialCandidate)
            .map(element => ({
              element,
              rect: element.getBoundingClientRect(),
              target: describeLayoutTarget(element)
            }))
            .sort((left, right) => left.rect.left - right.rect.left);
          if (children.length < 2) {
            continue;
          }

          for (let firstIndex = 0; firstIndex < children.length; firstIndex += 1) {
            const first = children[firstIndex];
            for (let secondIndex = firstIndex + 1; secondIndex < children.length; secondIndex += 1) {
              const second = children[secondIndex];
              if (second.rect.left > first.rect.right + tolerancePx) {
                break;
              }
              if (
                first.target.content_kind === 'container'
                && second.target.content_kind === 'container'
                && !first.target.surface.painted
                && !second.target.surface.painted
              ) {
                continue;
              }
              const geometry = resolveRelationGeometry(
                first.rect,
                second.rect,
                first.target.surface.painted && second.target.surface.painted
              );
              if (!geometry) {
                continue;
              }
              if (
                geometry.relation !== 'overlap'
                && isGroupedContact(parent, first.element, second.element)
              ) {
                continue;
              }

              const gridLayering = resolveGridLayering(parent, first.element, second.element);
              const signals = Array.from(new Set([
                ...buildSpatialIntentSignals(first.element),
                ...buildSpatialIntentSignals(second.element),
                ...(gridLayering ? ['grid_layering'] : [])
              ]));
              const intent = {
                likelihood: resolveIntentLikelihood(signals),
                signals
              };
              const visualPair = resolveVisualPair(first.target, second.target);
              const assessment = assessRelation({
                relation: geometry.relation,
                visualPair,
                first: first.target,
                second: second.target,
                intent
              });
              const relation = {
                scope: describeLayoutTarget(parent),
                first: first.target,
                second: second.target,
                relation: geometry.relation,
                visual_pair: visualPair,
                axis: geometry.axis,
                distance_px: Math.round(geometry.distance * 100) / 100,
                metrics: Object.fromEntries(
                  Object.entries(geometry.metrics).map(([key, value]) => [
                    key,
                    Math.round(value * 1000) / 1000
                  ])
                ),
                intent,
                attention: assessment.attention,
                reason_codes: assessment.reasonCodes,
                message: assessment.message
              };
              const pairKey = [
                first.target.locator.value,
                second.target.locator.value
              ].sort().join('::');
              const previous = relationsByPair.get(pairKey);
              if (
                !previous
                || attentionRank[relation.attention] > attentionRank[previous.attention]
                || (
                  attentionRank[relation.attention] === attentionRank[previous.attention]
                  && relation.distance_px < previous.distance_px
                )
              ) {
                relationsByPair.set(pairKey, relation);
              }
              if (relationsByPair.size >= maxRawRelations) {
                break;
              }
            }
            if (relationsByPair.size >= maxRawRelations) {
              break;
            }
          }
          if (relationsByPair.size >= maxRawRelations) {
            break;
          }
        }

        return Array.from(relationsByPair.values()).sort((left, right) => (
          attentionRank[right.attention] - attentionRank[left.attention]
          || relationRank[left.relation] - relationRank[right.relation]
          || left.distance_px - right.distance_px
        ));
      };
    """

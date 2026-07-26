"""文件功能：生成视觉检测 v2 汇总信息的浏览器端辅助函数。"""

from __future__ import annotations


def build_layout_summary_helpers() -> str:
    """构造四类视觉结果的计数、最高关注级别和紧凑汇总消息。"""

    return r"""
      const prioritizeLayoutResults = (items) => {
        const attentionRank = { none: 0, review: 1, likely_issue: 2 };
        return items
          .map((item, index) => ({ item, index }))
          .sort((left, right) => (
            attentionRank[right.item.attention] - attentionRank[left.item.attention]
            || left.index - right.index
          ))
          .map(entry => entry.item);
      };

      const buildLayoutSummary = (allResults, returnedResults) => {
        const attentionRank = { none: 0, review: 1, likely_issue: 2 };
        const labels = {
          text_layouts: '文本',
          item_groups: '分排',
          overflows: '越界',
          spatial_relations: '空间关系'
        };
        const totals = {};
        const returned = {};
        const attentionCounts = {};
        let highestAttention = 'none';
        for (const key of Object.keys(labels)) {
          totals[key] = allResults[key].length;
          returned[key] = returnedResults[key].length;
          attentionCounts[key] = returnedResults[key].filter(
            item => item.attention !== 'none'
          ).length;
          for (const item of returnedResults[key]) {
            if (attentionRank[item.attention] > attentionRank[highestAttention]) {
              highestAttention = item.attention;
            }
          }
        }
        const attentionTotal = Object.values(attentionCounts).reduce(
          (sum, count) => sum + count,
          0
        );
        const detail = Object.entries(attentionCounts)
          .filter(([, count]) => count > 0)
          .map(([key, count]) => `${labels[key]} ${count} 项`)
          .join('，');
        const truncated = Object.keys(labels).some(
          key => totals[key] > returned[key]
        );
        return {
          attention: highestAttention,
          message: attentionTotal
            ? `发现 ${attentionTotal} 项需要关注的视觉检测结果：${detail}。`
            : '未发现需要关注的视觉检测结果。',
          totals,
          returned,
          truncated
        };
      };
    """

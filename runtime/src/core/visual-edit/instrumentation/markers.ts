/**
 * 文件用途：集中定义可视化编辑派生源码与浏览器选择桥使用的保留 DOM marker。
 */

export const VISUAL_EDIT_NODE_ATTRIBUTE = 'data-page-visual-node-id'
export const VISUAL_EDIT_LOOP_ATTRIBUTE = 'data-page-visual-loop-node-id'
export const VISUAL_EDIT_LOOP_KEY_ATTRIBUTE = 'data-page-visual-loop-key'
export const VISUAL_EDIT_LOOP_INDEX_ATTRIBUTE = 'data-page-visual-loop-index'

export const VISUAL_EDIT_RESERVED_ATTRIBUTES = new Set([
  VISUAL_EDIT_NODE_ATTRIBUTE,
  VISUAL_EDIT_LOOP_ATTRIBUTE,
  VISUAL_EDIT_LOOP_KEY_ATTRIBUTE,
  VISUAL_EDIT_LOOP_INDEX_ATTRIBUTE,
])

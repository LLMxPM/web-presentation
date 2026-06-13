/** 文件功能：定义编辑器弹窗的统一尺寸规格、内容区预设与兼容解析工具。 */

export type DialogSize = 'compact' | 'standard' | 'wide' | 'canvas' | 'workbench'

export type DialogBodyPreset = 'auto' | 'dense' | 'editor' | 'split' | 'immersive'

export const DIALOG_SIZE_MAX_WIDTH: Record<DialogSize, string> = {
  compact: '560px',
  standard: '760px',
  wide: '1040px',
  canvas: '1280px',
  workbench: '1520px',
}

export const DIALOG_SIZE_TARGET_HEIGHT: Record<DialogSize, string> = {
  compact: 'min(78dvh, 640px)',
  standard: 'min(82dvh, 720px)',
  wide: 'min(84dvh, 780px)',
  canvas: 'min(88dvh, 860px)',
  workbench: 'calc(100dvh - (var(--dialog-shell-gap) * 2))',
}

export const DIALOG_BODY_PRESET_CLASS: Record<DialogBodyPreset, string> = {
  auto: 'dialog-body--auto',
  dense: 'dialog-body--dense',
  editor: 'dialog-body--editor',
  split: 'dialog-body--split',
  immersive: 'dialog-body--immersive',
}

/**
 * 解析弹窗面板最大宽度；优先使用旧版 width 兼容值，未提供时再回退到统一规格。
 * @param size 弹窗尺寸规格
 * @param width 旧版最大宽度字符串
 * @returns 可直接用于 CSS 变量的最大宽度值
 */
export function resolveDialogMaxWidth(size: DialogSize | undefined, width?: string): string {
  if (width) {
    return width
  }
  return DIALOG_SIZE_MAX_WIDTH[size ?? 'compact']
}

/**
 * 解析弹窗面板目标高度；统一按尺寸规格给出固定高度，避免内容继续撑开弹窗。
 * @param size 弹窗尺寸规格
 * @returns 可直接用于 CSS 变量的目标高度值
 */
export function resolveDialogTargetHeight(size: DialogSize | undefined): string {
  return DIALOG_SIZE_TARGET_HEIGHT[size ?? 'compact']
}

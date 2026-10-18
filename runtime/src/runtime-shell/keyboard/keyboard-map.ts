/**
 * 文件功能：定义 Runtime 快捷键的上下文、键位与动作映射，作为键盘行为的单一事实源。
 *
 * 约定：
 * 1. 布局层只负责把事件解析成动作并执行，不再散落键名判断；
 * 2. 带 Ctrl/Meta/Alt 的组合一律不参与映射，避免劫持浏览器与系统快捷键；
 * 3. 输入类元素由 isEditableKeyboardTarget 统一排除，调用方不需要重复判断。
 */

export type KeyboardContext = 'preview' | 'slideshow' | 'cards'

export type KeyboardAction =
  | 'next-page'
  | 'previous-page'
  | 'first-page'
  | 'last-page'
  | 'goto-page'
  | 'open-card-mode'
  | 'enter-slideshow'
  | 'open-presenter'
  | 'close-card-mode'

export interface KeyboardBinding {
  /** 规范化后的键名；空格统一为 space，字母为小写。 */
  keys: readonly string[]
  action: KeyboardAction
  /** 生效的界面上下文；同一键位可在多个上下文复用。 */
  contexts: readonly KeyboardContext[]
  /** 为 true 时必须按住 Shift；未声明时不限制 Shift。 */
  shift?: boolean
}

export interface ResolvedKeyboardCommand {
  action: KeyboardAction
  /** 数字跳页携带的目标页码。 */
  pageNumber?: number
}

/** 数字跳页接受 0-9；0 只用于两位数缓冲（如第 10 页），单独提交由调用方判为无效。 */
const DIGIT_KEYS = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9'] as const

/**
 * 全量键位表。
 *
 * - `preview`：非全屏预览；
 * - `slideshow`：根元素全屏放映；
 * - `cards`：卡片选择遮罩。
 *
 * 放映态不再由播放层独占空格，空格与方向键统一按下一页处理。
 */
export const KEYBOARD_BINDINGS: readonly KeyboardBinding[] = [
  {
    keys: ['arrowright', 'arrowdown', 'pagedown', 'space'],
    action: 'next-page',
    contexts: ['preview', 'slideshow', 'cards'],
  },
  {
    keys: ['arrowleft', 'arrowup', 'pageup'],
    action: 'previous-page',
    contexts: ['preview', 'slideshow', 'cards'],
  },
  { keys: ['home'], action: 'first-page', contexts: ['preview', 'slideshow'] },
  { keys: ['end'], action: 'last-page', contexts: ['preview', 'slideshow'] },
  { keys: DIGIT_KEYS, action: 'goto-page', contexts: ['preview', 'slideshow'] },
  { keys: ['o'], action: 'open-card-mode', contexts: ['preview'] },
  { keys: ['f'], action: 'enter-slideshow', contexts: ['preview'] },
  { keys: ['p'], action: 'open-presenter', contexts: ['preview', 'slideshow'], shift: true },
  { keys: ['escape'], action: 'close-card-mode', contexts: ['cards'] },
]

/**
 * 规范化键盘事件键名。
 * @param key KeyboardEvent.key 原始值
 * @returns 小写键名；空格统一为 space
 */
export function normalizeKeyboardKey(key: string): string {
  if (key === ' ' || key === 'Spacebar') {
    return 'space'
  }
  return key.toLowerCase()
}

/**
 * 判断事件目标是否属于可编辑区域。
 * @param target 键盘事件目标
 * @returns 输入框、文本域、下拉框或可编辑元素返回 true
 */
export function isEditableKeyboardTarget(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null
  if (!element || typeof element.tagName !== 'string') {
    return false
  }
  return element.tagName === 'INPUT'
    || element.tagName === 'TEXTAREA'
    || element.tagName === 'SELECT'
    || element.isContentEditable === true
}

/**
 * 把键盘事件解析为当前上下文对应的动作。
 * @param event 键盘事件
 * @param context 当前界面上下文
 * @returns 命中的命令；未命中或属于系统组合键时返回 null
 */
export function resolveKeyboardCommand(
  event: KeyboardEvent,
  context: KeyboardContext,
): ResolvedKeyboardCommand | null {
  if (event.altKey || event.ctrlKey || event.metaKey) {
    return null
  }

  const key = normalizeKeyboardKey(event.key)
  const binding = KEYBOARD_BINDINGS.find(item => item.contexts.includes(context)
    && item.keys.includes(key)
    && (item.shift === true ? event.shiftKey : true))
  if (!binding) {
    return null
  }

  if (binding.action === 'goto-page') {
    return { action: binding.action, pageNumber: Number(key) }
  }

  return { action: binding.action }
}

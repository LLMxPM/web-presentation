/**
 * 文件功能：提供 Editor UI 组件使用的 Tailwind class 条件组合与冲突消解能力。
 */

import { extendTailwindMerge } from 'tailwind-merge'

export type ClassDictionary = Record<string, boolean | null | undefined>
export type ClassValue = string | number | boolean | null | undefined | ClassDictionary | ClassValue[]

/** Editor 自定义 Token 工具类需显式登记，才能与默认 Tailwind 工具共同参与冲突消解。 */
const mergeEditorClasses = extendTailwindMerge({
  extend: {
    theme: {
      spacing: ['control-xs', 'control-sm', 'control-md', 'control-lg', 'icon-sm', 'icon-md', 'icon-lg'],
      radius: ['ui-sm', 'ui-md', 'ui-lg', 'ui-xl'],
      text: ['title-sm', 'title-md', 'title-lg'],
      shadow: ['popover', 'dialog', 'drag'],
    },
    classGroups: {
      duration: [{ duration: ['fast', 'normal'] }],
      z: [{ z: ['sticky', 'dock', 'dropdown', 'popover', 'dialog', 'toast'] }],
    },
  },
})

/**
 * 合并条件 class，并按 Tailwind 规则消解同一属性组的冲突。
 * @param values 支持字符串、条件对象和嵌套数组；假值会被忽略。
 * @returns 可直接传给 Vue `class` 属性的规范化 class 字符串。
 */
export function cn(...values: ClassValue[]): string {
  return mergeEditorClasses(flattenClassValues(values).join(' '))
}

/**
 * 展开调用方传入的条件 class，保持声明顺序供 tailwind-merge 判定最终覆盖关系。
 * @param values 任意层级的 class 值集合。
 * @returns 已过滤空值的原子 class 列表。
 */
function flattenClassValues(values: ClassValue[]): string[] {
  return values.flatMap(value => {
    if (!value) return []
    if (typeof value === 'string' || typeof value === 'number') return [String(value)]
    if (Array.isArray(value)) return flattenClassValues(value)
    return Object.entries(value)
      .filter(([, enabled]) => Boolean(enabled))
      .map(([className]) => className)
  })
}

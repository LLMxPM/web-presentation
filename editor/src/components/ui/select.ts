/**
 * 文件功能：定义通用下拉选择组件共享的选项和值类型。
 */

/** 下拉组件支持的基础值类型。 */
export type SelectPrimitive = string | number

/** 下拉组件支持的 modelValue 类型，兼容单选、多选和空值场景。 */
export type SelectModelValue = SelectPrimitive | SelectPrimitive[] | null

/** 通用下拉选项定义。 */
export interface SelectOption {
  label: string
  value: SelectPrimitive
  description?: string
  keywords?: string[]
  disabled?: boolean
}

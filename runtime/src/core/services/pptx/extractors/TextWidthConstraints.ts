/** 文件用途：统一识别 PPTX 文本扩宽需要保留的作者尺寸约束，区分最小宽度下限与实际宽度上界。 */

/**
 * 判断元素是否声明固定宽度、最大宽度或 Flex 基准尺寸。
 * min-width 只提供下限，不限制向右扩宽；auto/none 也不建立上界。
 * Tailwind 响应式与状态前缀只影响规则生效条件，识别时保留其实际尺寸语义。
 */
export function hasExplicitTextWidthConstraint(element: HTMLElement): boolean {
  const inlineConstraint = ['width', 'max-width', 'flex-basis'].some(property => {
    const value = element.style.getPropertyValue(property).trim()
    return Boolean(value && value !== 'auto' && !(property === 'max-width' && value === 'none'))
  })
  if (inlineConstraint) return true

  return Array.from(element.classList).some(className => {
    const utility = (className.split(':').pop() || className).replace(/^!/, '')
    return /^(?:max-)?w-(?!auto$|none$)/.test(utility) || /^basis-(?!auto$)/.test(utility)
  })
}

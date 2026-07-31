/**
 * 文件功能：定义页面可视化编辑器的 Tailwind 展示模型，并提供面向用户的分区与取值文案。
 */

export interface PageVisualEditTailwindOptionView {
  class_name: string
  label: string
}

export interface PageVisualEditTailwindGroupView {
  key: string
  label: string
  selectedClass: string
  baselineClass?: string
  options: PageVisualEditTailwindOptionView[]
}

export interface PageVisualEditTailwindSectionView {
  key: string
  label: string
  groups: PageVisualEditTailwindGroupView[]
}

const sectionDefinitions = [
  {
    key: 'layout',
    label: '布局方式',
    groups: ['display', 'position', 'flex-direction', 'flex-wrap', 'items', 'justify', 'grid-columns'],
  },
  {
    key: 'spacing',
    label: '间距',
    groups: ['gap', 'gap-x', 'gap-y', 'padding', 'padding-x', 'padding-y', 'margin', 'margin-x', 'margin-y'],
  },
  {
    key: 'sizing',
    label: '尺寸',
    groups: ['width', 'height', 'size'],
  },
  {
    key: 'typography',
    label: '文字',
    groups: ['text-size', 'text-alignment', 'text-align', 'font-weight', 'line-height', 'text-color'],
  },
  {
    key: 'appearance',
    label: '外观',
    groups: ['background-color', 'border-width', 'border-style', 'border-color', 'radius', 'shadow', 'opacity'],
  },
] as const

/**
 * 按产品语义分区 Tailwind 控件；目录中新出现的组统一放入“其他”。
 */
export function sectionTailwindGroups(
  groups: PageVisualEditTailwindGroupView[],
): PageVisualEditTailwindSectionView[] {
  const matchedKeys = new Set<string>()
  const sections: PageVisualEditTailwindSectionView[] = sectionDefinitions.flatMap((definition) => {
    const sectionGroups = groups.filter((group) => definition.groups.some(key => key === group.key))
    sectionGroups.forEach(group => matchedKeys.add(group.key))
    return sectionGroups.length
      ? [{ key: definition.key, label: definition.label, groups: sectionGroups }]
      : []
  })
  const remainingGroups = groups.filter(group => !matchedKeys.has(group.key))
  if (remainingGroups.length) {
    sections.push({ key: 'other', label: '其他', groups: remainingGroups })
  }
  return sections
}

/**
 * 将目录 class 值转换为业务文案；主流程不暴露 Tailwind token。
 */
export function tailwindClassLabel(
  group: PageVisualEditTailwindGroupView,
  className: string | undefined,
): string {
  if (!className) return '未设置'
  return group.options.find(option => option.class_name === className)?.label ?? '自定义值'
}

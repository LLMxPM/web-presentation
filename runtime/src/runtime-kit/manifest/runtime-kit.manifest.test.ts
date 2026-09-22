/**
 * 文件用途：验证 Runtime Kit 公开清单只包含 Backend/Agent 无法直接实现的运行时能力。
 */

import { describe, expect, it } from 'vitest'

import manifest from './runtime-kit.manifest.json'

const PUBLIC_CATEGORIES = ['asset', 'page', 'runtime']

interface PreviewField {
  type?: string
  description?: string
  default?: unknown
  options?: Array<{ label?: string; value: unknown }>
  agent_visible?: boolean
}

interface PreviewSchema {
  props?: Record<string, PreviewField>
  slots?: Record<string, unknown>
  presets?: Array<{ key?: string }>
}

describe('runtime kit manifest', () => {
  it('应声明 @runtime-kit 别名与收敛后的运行时能力', () => {
    const exportPaths = manifest.exports.map((item) => item.import_path)
    const exportNames = manifest.exports.map((item) => item.name)

    expect(manifest.alias).toBe('@runtime-kit')
    expect(exportPaths).toContain(
      '@runtime-kit/public/components/assets/AssetImage.v1.vue'
    )
    expect(exportPaths).toContain(
      '@runtime-kit/public/components/page/layout/DefaultContainer.v1.vue'
    )
    expect(exportPaths).toContain(
      '@runtime-kit/public/components/primitives/Icon.v1.vue'
    )
    expect(exportPaths).toContain(
      '@runtime-kit/public/components/primitives/ThemeLogo.v1.vue'
    )
    expect(exportPaths).toContain(
      '@runtime-kit/public/components/data/DataTable.v1.vue'
    )
    expect(exportNames).toContain('useRouteCatalog.v1')
    expect(exportNames).toContain('Connector.v1')
    expect(exportNames).toContain('useTheme.v1')
    expect(exportNames).toContain('useAssetFontFamily.v1')
    expect(exportNames).toContain('resolveAssetFontFamily.v1')
  })

  it('公开能力应使用文件名版本化命名', () => {
    const names = new Set<string>()
    const baseVersionKeys = new Set<string>()

    manifest.exports.forEach((item) => {
      expect(item.base_name, `${item.name} 缺少 base_name`).toEqual(expect.any(String))
      expect(item.version_no, `${item.name} 缺少 version_no`).toEqual(expect.any(Number))
      expect(item.version_no, `${item.name} version_no 必须为正整数`).toBeGreaterThan(0)
      expect(item.name).toBe(`${item.base_name}.v${item.version_no}`)
      expect(item.import_path, `${item.name} import_path 必须包含 .vN`).toMatch(/\.v\d+(?:\.[A-Za-z0-9]+)?$/)

      const key = `${item.kind}:${item.base_name}:v${item.version_no}`
      expect(names.has(item.name), `${item.name} 重复`).toBe(false)
      expect(baseVersionKeys.has(key), `${key} 重复`).toBe(false)
      names.add(item.name)
      baseVersionKeys.add(key)
    })
  })

  it('不应公开聚合渲染器、页面模板和样式区块组件', () => {
    const exportNames = manifest.exports.map((item) => item.name)

    expect(exportNames).not.toContain('AssetRenderer')
    expect(exportNames).not.toContain('DefaultCoverPage')
    expect(exportNames).not.toContain('DefaultContentPage')
    expect(exportNames).not.toContain('HeaderSection')
    expect(exportNames).not.toContain('FooterSection')
    expect(exportNames).not.toContain('Pagination')
    expect(exportNames).not.toContain('TableOfContents')
    expect(exportNames).not.toContain('useAssetMetadata')
    expect(exportNames).not.toContain('useIcon')
  })

  it('不应把 internal、runtime-shell 和 component-preview 暴露给页面源码', () => {
    const exportPaths = manifest.exports.map((item) => item.import_path)

    expect(exportPaths.some((path) => path.includes('PDF'))).toBe(false)
    expect(exportPaths.some((path) => path.includes('runtime-shell'))).toBe(
      false
    )
    expect(
      exportPaths.some((path) => path.includes('@runtime-kit/internal/'))
    ).toBe(false)
    expect(exportPaths.some((path) => path.includes('component-preview'))).toBe(
      false
    )
  })

  it('公开能力应只属于三个一级能力分组', () => {
    manifest.exports.forEach((item) => {
      expect(
        PUBLIC_CATEGORIES,
        `${item.name} 使用了非公开能力分组 ${item.category}`
      ).toContain(item.category)
    })
  })

  it('标签不应重复分类、类型或展示状态字段', () => {
    manifest.exports.forEach((item) => {
      const tags = item.capability?.tags || []
      const redundantTags = [
        item.category,
        item.kind,
        'doc-only',
        item.capability?.recommendation_level,
      ].filter(Boolean)

      redundantTags.forEach((tag) => {
        expect(
          tags,
          `${item.name} 的 tags 不应重复已有字段 ${tag}`
        ).not.toContain(tag)
      })
    })
  })

  it('所有能力应声明推荐等级，便于 Agent 排序', () => {
    manifest.exports.forEach((item) => {
      expect(
        ['default', 'advanced', 'internal-only'],
        `${item.name} 缺少 recommendation_level`
      ).toContain(item.capability?.recommendation_level)
    })
  })

  it('组件预览只允许默认推荐组件或明确高级组件按能力声明进入', () => {
    const previewableItems = manifest.exports.filter(
      (item) => item.capability?.previewable === true
    )
    const previewableNames = previewableItems.map((item) => item.base_name)

    expect(previewableNames).toEqual(
      expect.arrayContaining([
        'AssetImage',
        'AssetVideo',
        'AssetDrawio',
        'AssetMermaid',
        'AssetChart',
        'AssetFormula',
        'DefaultContainer',
        'Icon',
        'ThemeLogo',
        'DataTable',
      ])
    )
    expect(previewableNames).not.toContain('Connector')
    previewableItems.forEach((item) => {
      expect(item.kind).toBe('component')
      expect(
        item.capability?.preview_schema,
        `${item.name} 缺少 preview_schema`
      ).toEqual(expect.any(Object))
      expect(
        Object.keys(item.capability?.preview_schema || {}),
        `${item.name} 的 preview_schema 不应为空`
      ).not.toHaveLength(0)
      expect(
        item.capability?.preview_options,
        `${item.name} 缺少 preview_options`
      ).toEqual(expect.any(Object))
    })
  })

  it('可预览组件 schema 应覆盖真实可调字段和首屏示例输入', () => {
    const assetImageClass = 'w-full h-64 rounded-lg border border-border p-0 bg-transparent overflow-hidden'
    const assetVideoClass = 'w-full h-80 rounded-lg border border-border p-0 bg-transparent overflow-hidden'
    const assetDiagramClass = 'w-full h-96 rounded-lg border border-border p-0 bg-transparent overflow-hidden'
    const assetChartClass = 'w-full h-96 rounded-lg border border-border p-0 bg-transparent overflow-hidden'
    const assetFormulaClass = 'w-full h-20 rounded-lg border border-border p-0 bg-transparent text-primary overflow-hidden'
    const hiddenSurfaceProps = [
      'width',
      'height',
      'minHeight',
      'backgroundColor',
      'showBorder',
      'borderRadius',
      'padding',
      'textColor',
      'highlightColor',
    ]

    const assetImageProps = getPreviewProps('AssetImage')
    expect(Object.keys(assetImageProps)).toEqual(expect.arrayContaining([
      'name',
      'fallback',
      'alt',
      'class',
      'fit',
      'position',
    ]))
    expect(assetImageProps.fallback.default).toBe('图片资源无法渲染，请检查资源名称或资源内容。')
    expect(assetImageProps.fallback.agent_visible).toBe(false)
    expect(assetImageProps.class.default).toBe(assetImageClass)
    expect(assetImageProps.class.description).toContain('完整静态 Tailwind 类')
    expect(assetImageProps.class.description).toContain('外层图片框')
    expect(assetImageProps.class.description).toContain('max-h-*')
    expect(assetImageProps.class.description).toContain('object-contain')
    expect(assetImageProps.fit.description).toContain('边框框体内')
    expect(assetImageProps.fit.options).toEqual([
      { label: '完整显示', value: 'contain' },
      { label: '填满并裁切', value: 'cover' },
      { label: '拉伸填满', value: 'fill' },
      { label: '原始尺寸', value: 'none' },
    ])
    expect(assetImageProps.position.description).toContain('object-position')
    expect(assetImageProps).not.toHaveProperty('showFallbackPlaceholder')
    expect(getPresetKeys('AssetImage')).toEqual(expect.arrayContaining(['contain-preview', 'cover-banner']))

    const assetVideoProps = getPreviewProps('AssetVideo')
    expect(Object.keys(assetVideoProps)).toEqual(expect.arrayContaining([
      'posterFallback',
      'playsInline',
      'class',
      'fit',
      'position',
    ]))
    expect(assetVideoProps.fallback.default).toBe('视频资源无法渲染，请检查资源名称或资源内容。')
    expect(assetVideoProps.fallback.agent_visible).toBe(false)
    expect(assetVideoProps.posterFallback.agent_visible).toBe(false)
    expect(assetVideoProps.class.default).toBe(assetVideoClass)

    const assetDrawioProps = getPreviewProps('AssetDrawio')
    expect(Object.keys(assetDrawioProps)).toEqual(expect.arrayContaining([
      'name',
      'content',
      'fallback',
      'class',
    ]))
    expect(assetDrawioProps.content.type).toBe('textarea')
    expect(assetDrawioProps.fallback.default).toBe('Draw.io 资源无法渲染，请检查资源名称或 XML 内容。')
    expect(assetDrawioProps.fallback.agent_visible).toBe(false)
    expect(assetDrawioProps.class.default).toBe(assetDiagramClass)

    const assetMermaidProps = getPreviewProps('AssetMermaid')
    expect(Object.keys(assetMermaidProps)).toEqual(expect.arrayContaining([
      'content',
      'class',
      'theme',
      'previewEnabled',
    ]))
    expect(assetMermaidProps.content.type).toBe('textarea')
    expect(assetMermaidProps.fallback.default).toBe('Mermaid 资源无法渲染，请检查资源名称或图表源码。')
    expect(assetMermaidProps.fallback.agent_visible).toBe(false)
    expect(assetMermaidProps.class.default).toBe(assetDiagramClass)
    expect(assetMermaidProps.previewEnabled.default).toBe(true)

    const assetChartProps = getPreviewProps('AssetChart')
    expect(Object.keys(assetChartProps)).toEqual(expect.arrayContaining([
      'content',
      'class',
      'theme',
      'renderer',
    ]))
    expect(assetChartProps.content.type).toBe('textarea')
    expect(assetChartProps.fallback.default).toBe('Chart 资源无法渲染，请检查资源名称或 ECharts option 内容。')
    expect(assetChartProps.fallback.agent_visible).toBe(false)
    expect(assetChartProps.class.default).toBe(assetChartClass)
    expect(assetChartProps).not.toHaveProperty('notMerge')
    expect(assetChartProps).not.toHaveProperty('lazyUpdate')

    const assetFormulaProps = getPreviewProps('AssetFormula')
    expect(Object.keys(assetFormulaProps)).toEqual(expect.arrayContaining([
      'content',
      'displayMode',
      'fit',
      'class',
    ]))
    expect(assetFormulaProps.content.type).toBe('textarea')
    expect(assetFormulaProps.fallback.default).toBe('Formula 资源无法渲染，请检查资源名称或 LaTeX 内容。')
    expect(assetFormulaProps.fallback.agent_visible).toBe(false)
    expect(assetFormulaProps.fit.default).toBe('contain')
    expect(assetFormulaProps.fit.options?.map(option => option.value)).toEqual(['contain', 'none'])
    expect(assetFormulaProps.class.default).toBe(assetFormulaClass)
    expect(assetFormulaProps.class.description).toContain('公式颜色和字号')
    expect(assetFormulaProps.class.description).toContain('避免用 min-h')
    expect(assetFormulaProps).not.toHaveProperty('throwOnError')
    expect(assetFormulaProps).not.toHaveProperty('strict')
    expect(assetFormulaProps).not.toHaveProperty('trust')
    ;[
      assetImageProps,
      assetVideoProps,
      assetDrawioProps,
      assetMermaidProps,
      assetChartProps,
      assetFormulaProps,
    ].forEach((props) => {
      hiddenSurfaceProps.forEach((propName) => {
        expect(props).not.toHaveProperty(propName)
      })
    })

    const iconProps = getPreviewProps('Icon')
    expect(iconProps.class.default).toBe('size-16')
    expect(iconProps.strokeWidth.default).toBe(2)
    expect(iconProps.disabled.default).toBe(false)
    expect(iconProps.fallback.default).toBe('?')

    const themeLogoProps = getPreviewProps('ThemeLogo')
    expect(Object.keys(themeLogoProps)).toEqual(expect.arrayContaining([
      'variant',
      'alt',
      'size',
    ]))
    expect(themeLogoProps.variant.default).toBe('logo')
    expect(themeLogoProps.size.default).toBe(4)
    expect(themeLogoProps).not.toHaveProperty('width')
    expect(themeLogoProps).not.toHaveProperty('height')
    expect(themeLogoProps).not.toHaveProperty('fit')
    expect(themeLogoProps).not.toHaveProperty('fallbackSrc')
    expect(getPresetKeys('ThemeLogo')).toEqual(expect.arrayContaining(['theme-logo', 'theme-invert-logo']))

    const dataTableProps = getPreviewProps('DataTable')
    expect(Object.keys(dataTableProps)).toEqual(expect.arrayContaining([
      'rows',
      'width',
      'height',
      'class',
      'styles',
    ]))
    expect(dataTableProps.rows.type).toBe('json')
    expect(dataTableProps.rows.description).toContain('完整二维表格数据')
    expect(dataTableProps.width.default).toBe('100%')
    expect(dataTableProps.height.default).toBe('100%')
    expect(dataTableProps.class.default).toBe('text-sm rounded-lg border border-border overflow-hidden')
    expect(dataTableProps.styles.type).toBe('json')
    expect(dataTableProps.styles.description).toContain('table、cell、rows、columns、cells')
    expect(getPresetKeys('DataTable')).toEqual(expect.arrayContaining(['highlight-first-row', 'highlight-first-row-column']))
    expect(getPresetLabels('DataTable')).toEqual(expect.arrayContaining(['首行强调', '首行首列强调']))

    expect(getPresetKeys('DefaultContainer')).toEqual(expect.arrayContaining(['center-canvas', 'section-stack']))
  })

  it('preview schema 中 select 字段的默认值应命中 options', () => {
    const previewableItems = manifest.exports.filter(
      (item) => item.capability?.previewable === true
    )

    previewableItems.forEach((item) => {
      const schema = item.capability?.preview_schema as PreviewSchema
      Object.entries(schema.props || {}).forEach(([fieldName, field]) => {
        if (field.type !== 'select') {
          return
        }
        const optionValues = (field.options || []).map((option) => option.value)
        expect(
          optionValues,
          `${item.name}.${fieldName} 的默认值必须来自 options`
        ).toContain(field.default)
      })
    })
  })

  it('doc-only 能力应包含 usage、returns、return_example 和 constraints', () => {
    const docOnlyItems = manifest.exports.filter(
      (item) => item.capability?.previewable === false
    )

    expect(docOnlyItems.length).toBeGreaterThan(0)
    docOnlyItems.forEach((item) => {
      expect(item.capability?.usage, `${item.name} 缺少 usage`).toEqual(
        expect.arrayContaining([expect.any(String)])
      )
      expect(item.capability?.returns, `${item.name} 缺少 returns`).toEqual(
        expect.any(String)
      )
      expect(
        item.capability?.return_example,
        `${item.name} 缺少 return_example`
      ).toEqual(expect.arrayContaining([expect.any(String)]))
      expect(
        item.capability?.constraints,
        `${item.name} 缺少 constraints`
      ).toEqual(expect.arrayContaining([expect.any(String)]))
    })
  })

  it('资源能力 usage 应使用明确宽高并避免 min-h', () => {
    const renderAssetNames = [
      'AssetImage',
      'AssetVideo',
      'AssetDrawio',
      'AssetMermaid',
      'AssetChart',
      'AssetFormula',
    ]

    renderAssetNames.forEach((baseName) => {
      const item = getManifestItem(baseName)
      const usageText = (item.capability?.usage || []).join('\n')
      const returnExampleText = (item.capability?.return_example || []).join('\n')
      const constraintsText = (item.capability?.constraints || []).join('\n')
      const classDescription = getPreviewProps(baseName).class?.description || ''

      expect(usageText, `${baseName} usage 缺少明确宽高提示`).toContain('明确宽度和高度')
      expect(usageText, `${baseName} usage 缺少 min-h 禁用提示`).toContain('避免使用 min-h')
      expect(usageText, `${baseName} usage 示例不应包含 min-h 类`).not.toMatch(/\bmin-h-/)
      expect(usageText, `${baseName} usage 不应暗示可用等效 style`).not.toContain('等效 style')
      expect(returnExampleText, `${baseName} return_example 应提供 h- 高度示例`).toMatch(/\bh-[^\s"]+/)
      expect(returnExampleText, `${baseName} return_example 不应包含 min-h 类`).not.toMatch(/\bmin-h-/)
      expect(constraintsText, `${baseName} constraints 缺少明确宽高提示`).toContain('明确 width 和 height')
      expect(constraintsText, `${baseName} constraints 缺少 min-h 禁用提示`).toContain('避免用 min-h')
      expect(classDescription, `${baseName} class 描述缺少 min-h 禁用提示`).toContain('避免用 min-h')
    })

    const assetImage = getManifestItem('AssetImage')
    const assetImageGuidance = [
      ...(assetImage.capability?.usage || []),
      ...(assetImage.capability?.constraints || []),
    ].join('\n')
    expect(assetImageGuidance).toContain('不要把 object-contain/object-cover 写进 AssetImage 的 class')
    expect(assetImageGuidance).toContain('style="max-height:..."')
    expect(assetImageGuidance).toContain('AssetImage 自身必须有确定高度')

    ;[
      'useAssetSrc',
      'useAssetBackground',
      'resolveResourcePath',
    ].forEach((baseName) => {
      const item = getManifestItem(baseName)
      const usageText = (item.capability?.usage || []).join('\n')
      const constraintsText = (item.capability?.constraints || []).join('\n')

      expect(usageText, `${baseName} usage 缺少消费侧宽高提示`).toContain('明确宽度和高度')
      expect(usageText, `${baseName} usage 缺少自由高度提示`).toContain('自由高度')
      expect(constraintsText, `${baseName} constraints 缺少调用方宽高提示`).toContain('width 和 height')
    })
  })

  it('所有公开能力都应包含面向 Backend/Agent 的说明字段', () => {
    manifest.exports.forEach((item) => {
      expect(
        item.capability?.display_name,
        `${item.name} 缺少 display_name`
      ).toEqual(expect.any(String))
      expect(item.capability?.summary, `${item.name} 缺少 summary`).toEqual(
        expect.any(String)
      )
      expect(item.capability?.audiences, `${item.name} 缺少 audiences`).toEqual(
        expect.arrayContaining(['backend', 'agent'])
      )
      expect(
        item.capability?.constraints,
        `${item.name} 缺少 constraints`
      ).toEqual(expect.arrayContaining([expect.any(String)]))
    })
  })
})

function getPreviewProps(componentName: string): Record<string, PreviewField> {
  const schema = getPreviewSchema(componentName)
  return schema.props || {}
}

function getPresetKeys(componentName: string): string[] {
  const schema = getPreviewSchema(componentName)
  return (schema.presets || []).map((preset) => String(preset.key || ''))
}

function getPresetLabels(componentName: string): string[] {
  const schema = getPreviewSchema(componentName)
  return (schema.presets || []).map((preset) => String((preset as { label?: string }).label || ''))
}

function getPreviewSchema(componentName: string): PreviewSchema {
  const item = getManifestItem(componentName)
  const schema = item?.capability?.preview_schema
  expect(schema, `${componentName} 缺少 preview_schema`).toEqual(expect.any(Object))
  return schema as PreviewSchema
}

function getManifestItem(componentName: string) {
  const item = manifest.exports.find((exportItem) => exportItem.base_name === componentName)
  expect(item, `未找到 Runtime Kit 能力 ${componentName}`).toBeTruthy()
  return item!
}

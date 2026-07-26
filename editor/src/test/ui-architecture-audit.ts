/**
 * 文件功能：提供 Editor UI 架构契约测试所需的只读源码盘点能力。
 */
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

/** UI 迁移统计的最终精确基线；只允许已登记的原生控件豁免。 */
export interface UiMigrationBaseline {
  legacyClassReferences: number
  nakedButtons: number
  nakedInputs: number
  nakedTextareas: number
  nakedSelects: number
}

/** 单个源码文件的相对路径与文本内容。 */
export interface EditorSourceFile {
  relativePath: string
  content: string
}

/** 业务源码中一处原生控件的定位信息。 */
export interface NakedControlOccurrence {
  relativePath: string
  line: number
  tag: 'button' | 'input' | 'textarea' | 'select'
  openingTag: string
}

/** 已审核的原生控件豁免；必须同时限制路径、标签、语义属性与数量。 */
interface NativeControlExemption {
  relativePath: string
  tag: NakedControlOccurrence['tag']
  expectedCount: number
  reason: string
  attributePattern?: RegExp
}

const SOURCE_EXTENSIONS = new Set(['.css', '.scss', '.ts', '.tsx', '.vue'])
const EDITOR_AUDIT_EXTENSIONS = new Set([...SOURCE_EXTENSIONS, '.py'])
const TEST_FILE_PATTERN = /(?:\.test|\.spec)\.[cm]?[jt]sx?$/
const SOURCE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const EDITOR_ROOT = resolve(SOURCE_ROOT, '..')
const LEGACY_CLASS_TOKEN_PATTERN = /^(?:btn|input|card)(?:-[\w-]+)?$/
const LEGACY_GLOBAL_CLASS_NAMES = new Set(['btn', 'input', 'card'])
const RETIRED_UI_PRIMITIVE_PATTERN = /\bBase(?:Button|Input)\b/g
const EDITOR_AUDIT_IGNORED_DIRECTORIES = new Set(['node_modules', 'dist', 'coverage', 'test-results'])
const NAKED_CONTROL_PATTERN = /<(button|input|textarea|select)\b[^>]*>/gi

/**
 * 业务区仅可保留以下无法由通用 Primitive 安全替代的原生控件。
 * 文件上传、颜色选择、内联即时数值、富文本选区以及主题预览示意均依赖原生 DOM 行为。
 */
const NATIVE_CONTROL_EXEMPTIONS: NativeControlExemption[] = [
  { relativePath: 'views/ComponentsView.vue', tag: 'input', expectedCount: 1, reason: '文件导入', attributePattern: /\btype\s*=\s*["']file["']/i },
  { relativePath: 'views/AssetsView.vue', tag: 'input', expectedCount: 3, reason: '资源文件选择', attributePattern: /\btype\s*=\s*["']file["']/i },
  { relativePath: 'components/agent/AgentComposer.vue', tag: 'input', expectedCount: 1, reason: '图片附件选择', attributePattern: /\btype\s*=\s*["']file["']/i },
  { relativePath: 'views/WorkspaceStylesView.vue', tag: 'input', expectedCount: 1, reason: '样式包导入', attributePattern: /\btype\s*=\s*["']file["']/i },
  { relativePath: 'views/ThemesView.vue', tag: 'input', expectedCount: 3, reason: '字体文件选择', attributePattern: /\btype\s*=\s*["']file["']/i },
  { relativePath: 'views/ProjectsView.vue', tag: 'input', expectedCount: 1, reason: '模板包导入', attributePattern: /\btype\s*=\s*["']file["']/i },
  { relativePath: 'components/project/ProjectSuggestedReferenceAssetsDialog.vue', tag: 'input', expectedCount: 1, reason: '参考资源选择', attributePattern: /\btype\s*=\s*["']file["']/i },
  { relativePath: 'components/theme/ThemeEditorDialog.vue', tag: 'input', expectedCount: 2, reason: '原生颜色选择器', attributePattern: /\btype\s*=\s*["']color["']/i },
  { relativePath: 'components/component-preview/ComponentPreviewPlacementToolbar.vue', tag: 'input', expectedCount: 6, reason: '内联即时数值编辑', attributePattern: /\binputmode\s*=\s*["']numeric["']/i },
  { relativePath: 'components/component-preview/ComponentPreviewReleaseToolbar.vue', tag: 'input', expectedCount: 6, reason: '内联即时数值编辑', attributePattern: /\binputmode\s*=\s*["']numeric["']/i },
  { relativePath: 'components/agent/AgentComposer.vue', tag: 'textarea', expectedCount: 1, reason: '自动高度与 Enter 提交' },
  { relativePath: 'components/page-detail/visual-edit/PageVisualEditRichTextNodeEditor.vue', tag: 'textarea', expectedCount: 1, reason: '原生选区追踪' },
  { relativePath: 'components/theme/ThemePreviewCard.vue', tag: 'button', expectedCount: 1, reason: '主题按钮样式示意' },
  { relativePath: 'components/component-preview/ComponentPreviewWorkbench.vue', tag: 'button', expectedCount: 1, reason: '简化模式透明缩放触发区' },
  { relativePath: 'components/patterns/PageHeader.vue', tag: 'button', expectedCount: 1, reason: 'Popover 描述触发按钮' },
  { relativePath: 'components/theme/FontEditorDialog.vue', tag: 'button', expectedCount: 1, reason: '字体声明 Popover 说明触发按钮', attributePattern: /\baria-label\s*=\s*["']字体声明说明["']/i },
  { relativePath: 'components/patterns/SimpleSearchBar.vue', tag: 'input', expectedCount: 1, reason: '搜索栏输入框' },
  { relativePath: 'components/patterns/SimpleSearchBar.vue', tag: 'button', expectedCount: 1, reason: '搜索栏清空按钮' },
  { relativePath: 'components/agent/AgentSessionControls.vue', tag: 'button', expectedCount: 1, reason: '会话列表项切换按钮' },
  { relativePath: 'components/nav/ProjectQuickSwitcher.vue', tag: 'button', expectedCount: 2, reason: '快速切换触发器与项目列表项' },
  { relativePath: 'components/agent/AgentVisualToolCard.vue', tag: 'button', expectedCount: 2, reason: '图片预览触发按钮' },
  { relativePath: 'components/project/SuggestedComponentsSelectorPanel.vue', tag: 'button', expectedCount: 1, reason: '建议组件选择触发按钮' },
  { relativePath: 'components/project/ProjectSuggestedReferenceAssetsDialog.vue', tag: 'button', expectedCount: 1, reason: '建议资源整卡片选择触发区' },
  { relativePath: 'components/page/PageCreateCard.vue', tag: 'button', expectedCount: 1, reason: '整卡片新增页面触发区' },
  { relativePath: 'components/project/ProjectCreateCard.vue', tag: 'button', expectedCount: 1, reason: '整卡片新增项目触发区' },
  { relativePath: 'components/page/PageCard.vue', tag: 'button', expectedCount: 1, reason: '页面编码内联复制触发按钮', attributePattern: /\baria-label\s*=\s*["']复制页面名称和编码["']/i },
]

/**
 * 递归读取产品源码，排除测试文件，避免测试夹具影响架构盘点结果。
 * @param directory 当前遍历目录
 * @returns 符合盘点范围的源码文件
 */
function collectSourceFiles(directory: string): EditorSourceFile[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const absolutePath = resolve(directory, entry.name)
    if (entry.isDirectory()) {
      return entry.name === 'test' ? [] : collectSourceFiles(absolutePath)
    }

    const extension = entry.name.slice(entry.name.lastIndexOf('.'))
    if (!SOURCE_EXTENSIONS.has(extension) || TEST_FILE_PATTERN.test(entry.name)) {
      return []
    }

    return [{
      relativePath: relative(SOURCE_ROOT, absolutePath).split(sep).join('/'),
      content: readFileSync(absolutePath, 'utf8'),
    }]
  })
}

/** 读取 Editor 产品源码，供多个静态架构契约共用。 */
export function getEditorSourceFiles(): EditorSourceFile[] {
  return collectSourceFiles(SOURCE_ROOT)
}

/**
 * 读取 Editor 内需要接受架构契约检查的源码、测试及脚本模板。
 * @param directory 当前遍历目录
 * @returns 可被 UI 架构规则扫描的文件
 */
function collectEditorAuditFiles(directory: string): EditorSourceFile[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const absolutePath = resolve(directory, entry.name)
    if (entry.isDirectory()) {
      return EDITOR_AUDIT_IGNORED_DIRECTORIES.has(entry.name) ? [] : collectEditorAuditFiles(absolutePath)
    }

    const extension = entry.name.slice(entry.name.lastIndexOf('.'))
    if (!EDITOR_AUDIT_EXTENSIONS.has(extension)) {
      return []
    }

    return [{
      relativePath: relative(EDITOR_ROOT, absolutePath).split(sep).join('/'),
      content: readFileSync(absolutePath, 'utf8'),
    }]
  })
}

/** 读取全 Editor 可执行源码与模板，确保已退役组件不会在测试或脚本中回流。 */
export function getEditorAuditFiles(): EditorSourceFile[] {
  return collectEditorAuditFiles(EDITOR_ROOT)
}

/**
 * 按相对于 editor/ 的路径读取公共入口或构建配置。
 * @param relativePath 相对于 editor/ 的文件路径
 */
export function readEditorFile(relativePath: string): string {
  return readFileSync(resolve(EDITOR_ROOT, relativePath), 'utf8')
}

/**
 * 提取源码中的样式文本；Vue 文件只检查 style 区块，避免模板、脚本中的属性名被误识别为 CSS。
 * @param sourceFile 待检查的 Editor 源码文件
 */
function getStyleBlocks(sourceFile: EditorSourceFile): string[] {
  if (sourceFile.relativePath.endsWith('.css') || sourceFile.relativePath.endsWith('.scss')) {
    return [sourceFile.content]
  }

  return [...sourceFile.content.matchAll(/<style(?:\s[^>]*)?>([\s\S]*?)<\/style>/gi)].map(match => match[1])
}

/**
 * 读取 CSS 规则选择器中的旧类定义，不读取样式声明体，防止属性访问和字符串字面量造成误计。
 * @param styleBlock 单个 CSS/SCSS 样式文本
 */
function getLegacyClassSelectors(styleBlock: string): string[] {
  const selectors: string[] = []
  for (const rule of styleBlock.matchAll(/([^{}]+)\{/g)) {
    const selector = rule[1].replace(/\/\*[\s\S]*?\*\//g, '').trim()
    if (selector.startsWith('@')) {
      continue
    }

    for (const classMatch of selector.matchAll(/\.([\w-]+)\b/g)) {
      if (LEGACY_CLASS_TOKEN_PATTERN.test(classMatch[1])) {
        selectors.push(classMatch[1])
      }
    }
  }
  return selectors
}

/**
 * 读取模板静态 class 属性中的完整 class token；动态对象和普通对象属性均不纳入统计。
 * @param sourceFile 待检查的 Editor 源码文件
 */
function getStaticLegacyClassTokens(sourceFile: EditorSourceFile): string[] {
  if (!sourceFile.relativePath.endsWith('.vue')) {
    return []
  }

  const tokens: string[] = []
  for (const attribute of sourceFile.content.matchAll(/(?<![:\w-])class\s*=\s*(["'])([\s\S]*?)\1/g)) {
    for (const token of attribute[2].split(/\s+/)) {
      if (LEGACY_CLASS_TOKEN_PATTERN.test(token)) {
        tokens.push(token)
      }
    }
  }
  return tokens
}

/**
 * 收集旧全局类的 CSS 定义位置，供防回流硬门禁输出可定位的违规项。
 * @param sourceFiles 已读取的 Editor 产品源码
 */
export function getLegacyGlobalClassDefinitions(sourceFiles = getEditorSourceFiles()): string[] {
  return sourceFiles.flatMap((sourceFile) => getStyleBlocks(sourceFile)
    .flatMap(getLegacyClassSelectors)
    .filter(className => LEGACY_GLOBAL_CLASS_NAMES.has(className))
    .map(className => `${sourceFile.relativePath}:.${className}`))
}

/**
 * 收集已退役 UI Primitive 的出现位置，覆盖产品源码、测试和脚本模板。
 * @param sourceFiles 已读取的 Editor 审计文件
 * @returns 违反退役组件禁用规则的位置
 */
export function getRetiredUiPrimitiveReferences(sourceFiles = getEditorAuditFiles()): string[] {
  return sourceFiles.flatMap((sourceFile) => [...sourceFile.content.matchAll(RETIRED_UI_PRIMITIVE_PATTERN)]
    .map(match => `${sourceFile.relativePath}:${match.index}`))
}

/**
 * 收集业务区裸原生控件并保留行号，便于契约失败时直接定位回流代码。
 * @param sourceFiles 已读取的 Editor 产品源码
 * @returns 排除 components/ui 后的所有原生控件
 */
export function getNakedControlOccurrences(sourceFiles = getEditorSourceFiles()): NakedControlOccurrence[] {
  return sourceFiles
    .filter(sourceFile => !sourceFile.relativePath.startsWith('components/ui/'))
    .flatMap((sourceFile) => [...sourceFile.content.matchAll(NAKED_CONTROL_PATTERN)].map((match) => ({
      relativePath: sourceFile.relativePath,
      line: sourceFile.content.slice(0, match.index).split('\n').length,
      tag: match[1].toLowerCase() as NakedControlOccurrence['tag'],
      openingTag: match[0],
    })))
}

/** 查找与裸控件路径、标签和属性语义均匹配的豁免规则。 */
function findNativeControlExemption(control: NakedControlOccurrence): NativeControlExemption | undefined {
  return NATIVE_CONTROL_EXEMPTIONS.find(exemption => (
    exemption.relativePath === control.relativePath
    && exemption.tag === control.tag
    && (!exemption.attributePattern || exemption.attributePattern.test(control.openingTag))
  ))
}

/**
 * 返回不在原生控件白名单内，或超出白名单数量的裸控件；每条均包含文件与行号。
 * @param sourceFiles 已读取的 Editor 产品源码
 * @returns 可直接定位的架构违规说明
 */
export function getNakedControlViolations(sourceFiles = getEditorSourceFiles()): string[] {
  const controlsByExemption = new Map<NativeControlExemption, NakedControlOccurrence[]>()
  const violations: string[] = []

  for (const control of getNakedControlOccurrences(sourceFiles)) {
    const exemption = findNativeControlExemption(control)
    if (!exemption) {
      violations.push(`${control.relativePath}:${control.line}:<${control.tag}> 不在原生控件白名单内`)
      continue
    }

    const matchedControls = controlsByExemption.get(exemption) ?? []
    matchedControls.push(control)
    controlsByExemption.set(exemption, matchedControls)
    if (matchedControls.length > exemption.expectedCount) {
      violations.push(`${control.relativePath}:${control.line}:<${control.tag}> 超出“${exemption.reason}”豁免数量 ${exemption.expectedCount}`)
    }
  }

  for (const exemption of NATIVE_CONTROL_EXEMPTIONS) {
    const actualCount = controlsByExemption.get(exemption)?.length ?? 0
    if (actualCount < exemption.expectedCount) {
      violations.push(`${exemption.relativePath}:<${exemption.tag}> “${exemption.reason}”豁免数量应为 ${exemption.expectedCount}，实际为 ${actualCount}`)
    }
  }

  return violations
}

/**
 * 统计旧样式与业务区裸控件，用于验证最终精确基线。
 * @param sourceFiles 已读取的 Editor 产品源码
 */
export function collectUiMigrationStats(sourceFiles = getEditorSourceFiles()): UiMigrationBaseline {
  const stats: UiMigrationBaseline = {
    legacyClassReferences: 0,
    nakedButtons: 0,
    nakedInputs: 0,
    nakedTextareas: 0,
    nakedSelects: 0,
  }

  for (const sourceFile of sourceFiles) {
    stats.legacyClassReferences += getStyleBlocks(sourceFile).flatMap(getLegacyClassSelectors).length
    stats.legacyClassReferences += getStaticLegacyClassTokens(sourceFile).length

  }

  for (const control of getNakedControlOccurrences(sourceFiles)) {
    if (control.tag === 'button') stats.nakedButtons += 1
    if (control.tag === 'input') stats.nakedInputs += 1
    if (control.tag === 'textarea') stats.nakedTextareas += 1
    if (control.tag === 'select') stats.nakedSelects += 1
  }

  return stats
}

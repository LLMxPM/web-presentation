/**
 * 文件功能：为组件库条目生成可复制的 import 路径与 import 语句。
 */
import type { RuntimeKitComponentCapabilityItem, WorkspaceComponentItem } from '@/types/api'

export interface ComponentImportUsage {
  importPath: string
  importStatement: string
}

/**
 * 根据工作空间组件当前发布版本生成导入用法。
 * @param component 工作空间组件条目，必须包含编码、名称与当前发布版本号
 * @returns 可复制的 import 用法；未发布或缺少编码时返回 null
 */
export function buildWorkspaceComponentImportUsage(
  component: Pick<WorkspaceComponentItem, 'code' | 'name' | 'import_name' | 'current_version_no'>,
): ComponentImportUsage | null {
  const componentCode = normalizeText(component.code)
  const versionNo = Number(component.current_version_no)
  if (!componentCode || !Number.isInteger(versionNo) || versionNo <= 0) {
    return null
  }

  const importPath = `@workspace-components/${componentCode}/v/${versionNo}`
  const importName = toValidImportIdentifier(component.import_name)
    || toValidImportIdentifier(component.name)
    || toValidImportIdentifier(componentCode)
    || 'WorkspaceComponent'
  return buildDefaultImportUsage(importName, importPath)
}

/**
 * 根据 Runtime Kit 组件能力生成导入用法。
 * @param item Runtime Kit 能力条目，仅 component 类型会生成默认导入
 * @returns 可复制的 import 用法；非组件能力或缺少路径时返回 null
 */
export function buildRuntimeKitComponentImportUsage(
  item: Pick<RuntimeKitComponentCapabilityItem, 'kind' | 'name' | 'display_name' | 'import_path'>,
): ComponentImportUsage | null {
  const importPath = normalizeText(item.import_path)
  if (item.kind !== 'component' || !importPath) {
    return null
  }

  const importName = toValidImportIdentifier(item.name) || toValidImportIdentifier(item.display_name) || 'RuntimeKitComponent'
  return buildDefaultImportUsage(importName, importPath)
}

/**
 * 将展示名或组件编码转换为合法的默认导入标识符。
 * @param rawName 原始展示名、能力名称或组件编码
 * @returns PascalCase 标识符；无法转换时返回空字符串
 */
export function toValidImportIdentifier(rawName: string | null | undefined) {
  const normalizedName = normalizeText(rawName)
  if (!normalizedName) {
    return ''
  }

  const tokens = normalizedName.split(/[^A-Za-z0-9_$]+/).filter(Boolean)
  if (tokens.length === 0) {
    return ''
  }

  let transformed = tokens.map(token => token.slice(0, 1).toUpperCase() + token.slice(1)).join('')
  if (/^[0-9]/.test(transformed)) {
    transformed = `Component${transformed}`
  }
  return transformed
}

/**
 * 组装默认导入语句，保持页面源码和组件源码中可直接粘贴使用。
 * @param importName 默认导入标识符
 * @param importPath 模块导入路径
 * @returns import 路径与完整语句
 */
function buildDefaultImportUsage(importName: string, importPath: string): ComponentImportUsage {
  return {
    importPath,
    importStatement: `import ${importName} from '${importPath}'`,
  }
}

/**
 * 归一化用户可见文本，避免空白字符进入 import 语句。
 * @param value 待归一化的字符串值
 * @returns 去除首尾空白后的字符串
 */
function normalizeText(value: string | null | undefined) {
  return String(value || '').trim()
}

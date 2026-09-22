/**
 * 文件用途：编排 Vue SFC、脚本数组与模板语义分析，生成页面可视化编辑的版本化 Manifest。
 */

import { createHash } from 'node:crypto'

import { parse, type SFCParseResult } from '@vue/compiler-sfc'

import {
  PAGE_VISUAL_EDIT_PROTOCOL_VERSION,
  type VisualEditDiagnostic,
  type VisualEditSfcManifest,
  type VisualEditTemplateNode,
} from '../protocol'
import {
  analyzeScript,
  type ScriptCollectionDefinition,
} from './analyze-script'
import { analyzeTemplate } from './analyze-template'
import type { CompilerRootNode } from './compiler-node-types'
import {
  createStableId,
  normalizeModulePath,
  toSourceRange,
} from './template-expression'
import { runtimeVisualTailwindCatalog } from '../tailwind/catalog'

export interface AnalyzeVisualEditSfcOptions {
  modulePath: string
  filename?: string
}

/**
 * 解析 Vue SFC 并生成只读分析 Manifest。该函数不执行页面代码，也不修改传入源码。
 * @param source 完整 Vue SFC 源码
 * @param options 模块逻辑路径与可选文件名
 * @returns 模板层级、绑定定位和只读原因
 */
export function analyzeVisualEditSfc(
  source: string,
  options: AnalyzeVisualEditSfcOptions
): VisualEditSfcManifest {
  const modulePath = normalizeModulePath(options.modulePath)
  const sourceHash = createHash('sha256').update(source).digest('hex')
  const diagnostics: VisualEditDiagnostic[] = []
  const root = buildRootNode(modulePath, source.length)
  const parsed = parse(source, {
    filename: options.filename || modulePath || 'VisualEditPage.vue',
    sourceMap: false,
  })

  appendParseDiagnostics(parsed, diagnostics)
  const { descriptor } = parsed
  if (
    !descriptor.template?.ast ||
    (descriptor.template.lang && descriptor.template.lang !== 'html')
  ) {
    diagnostics.push({
      severity: 'warning',
      code: 'TEMPLATE_UNSUPPORTED',
      message: '首版可视化编辑仅支持标准 HTML Vue template。',
      sourceRange: descriptor.template
        ? toSourceRange(descriptor.template.loc)
        : undefined,
    })
    return buildManifest(modulePath, sourceHash, root, diagnostics)
  }

  const scriptAnalysis = descriptor.scriptSetup
    ? analyzeScript(
        descriptor.scriptSetup.content,
        descriptor.scriptSetup.loc.start.offset,
        descriptor.scriptSetup.lang || 'ts',
        modulePath
      )
    : {
        collections: new Map<string, ScriptCollectionDefinition>(),
        jsonSources: new Map(),
      }
  const templateResult = analyzeTemplate(
    descriptor.template.ast as unknown as CompilerRootNode,
    {
      modulePath,
      collections: scriptAnalysis.collections,
      jsonSources: scriptAnalysis.jsonSources,
      diagnostics,
      rootNodeId: root.nodeId,
    }
  )
  root.children = templateResult.children
  root.bindings = templateResult.bindings

  return buildManifest(modulePath, sourceHash, root, diagnostics, [
    ...scriptAnalysis.jsonSources.values(),
  ])
}

/**
 * 构造协议根节点，使无模板或解析失败时仍返回结构稳定的结果。
 */
function buildRootNode(
  modulePath: string,
  sourceLength: number
): VisualEditTemplateNode {
  return {
    nodeId: createStableId('node', modulePath, 'root'),
    kind: 'root',
    tag: '#document',
    sourceRange: { start: 0, end: sourceLength },
    templateActions: {
      canDuplicate: false,
      canDelete: false,
      readonlyReason: 'STRUCTURE_ROOT_UNSUPPORTED',
    },
    bindings: [],
    children: [],
  }
}

/**
 * 把编译器解析错误归一化为协议诊断，不泄漏不稳定的错误对象结构。
 */
function appendParseDiagnostics(
  parsed: SFCParseResult,
  diagnostics: VisualEditDiagnostic[]
): void {
  for (const error of parsed.errors) {
    diagnostics.push({
      severity: 'error',
      code: 'SFC_PARSE_ERROR',
      message: typeof error === 'string' ? error : error.message,
    })
  }
}

/**
 * 汇总最终 Manifest，集中固定协议版本字段。
 */
function buildManifest(
  modulePath: string,
  sourceHash: string,
  root: VisualEditTemplateNode,
  diagnostics: VisualEditDiagnostic[],
  jsonSources: import('../protocol').VisualEditJsonSource[] = []
): VisualEditSfcManifest {
  return {
    protocolVersion: PAGE_VISUAL_EDIT_PROTOCOL_VERSION,
    modulePath,
    sourceHash,
    tailwindCatalog: runtimeVisualTailwindCatalog,
    jsonSources,
    root,
    diagnostics,
  }
}

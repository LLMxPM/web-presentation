/**
 * 文件功能：集中封装 Monaco 的初始化、语言映射、主题和补全配置。
 */
import 'monaco-editor/min/vs/editor/editor.main.css'

import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import jsonWorker from 'monaco-editor/esm/vs/language/json/json.worker?worker'
import cssWorker from 'monaco-editor/esm/vs/language/css/css.worker?worker'
import htmlWorker from 'monaco-editor/esm/vs/language/html/html.worker?worker'
import tsWorker from 'monaco-editor/esm/vs/language/typescript/ts.worker?worker'
import * as monaco from 'monaco-editor'

import type {
  EditorLanguage,
  EditorThemeMode,
  MonacoCompletionConfig,
  MonacoCompletionKind,
  MonacoCompletionSuggestion,
} from '@/types/monaco'

const MONACO_THEME_NAMES = {
  dark: 'codex-dark',
  light: 'codex-light',
} as const

const LANGUAGE_ALIASES: Record<EditorLanguage, string> = {
  vue: 'html',
  html: 'html',
  javascript: 'javascript',
  typescript: 'typescript',
  json: 'json',
  yaml: 'yaml',
  plaintext: 'plaintext',
  css: 'css',
}

let initialized = false
let themeRegistered = false

/**
 * 初始化 Monaco 运行环境，配置 worker、本地化和统一主题。
 */
export async function initializeMonaco() {
  if (!initialized) {
    const environment = {
      locale: 'zh-cn',
      availableLanguages: { '*': 'zh-cn' },
      getWorker(_: unknown, label: string) {
        if (label === 'json') return new jsonWorker()
        if (['css', 'scss', 'less'].includes(label)) return new cssWorker()
        if (['html', 'handlebars', 'razor'].includes(label)) return new htmlWorker()
        if (['typescript', 'javascript'].includes(label)) return new tsWorker()
        return new editorWorker()
      },
    }
    ;(globalThis as typeof globalThis & { MonacoEnvironment?: typeof environment }).MonacoEnvironment = environment

    ;(globalThis as typeof globalThis & { _VSCODE_NLS_LANGUAGE?: string })._VSCODE_NLS_LANGUAGE = 'zh-cn'

    initialized = true
  }

  if (!themeRegistered) {
    registerEditorTheme()
    themeRegistered = true
  }

  return monaco
}

/**
 * 注册统一的浅色编辑器主题，保持后台界面视觉一致。
 */
function registerEditorTheme() {
  monaco.editor.defineTheme(MONACO_THEME_NAMES.dark, {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: 'comment', foreground: '64748B' },
      { token: 'keyword', foreground: 'A78BFA' },
      { token: 'string', foreground: '34D399' },
      { token: 'number', foreground: 'FB923C' },
      { token: 'tag', foreground: '60A5FA' },
    ],
    colors: {
      'editor.background': '#020617',
      'editor.foreground': '#E2E8F0',
      'editor.lineHighlightBackground': '#0F172A',
      'editorLineNumber.foreground': '#475569',
      'editorLineNumber.activeForeground': '#CBD5E1',
      'editorCursor.foreground': '#60A5FA',
      'editor.selectionBackground': '#1D4ED84D',
      'editor.inactiveSelectionBackground': '#33415555',
      'editorWhitespace.foreground': '#334155',
      'editorIndentGuide.background1': '#1E293B',
      'editorIndentGuide.activeBackground1': '#475569',
    },
  })

  monaco.editor.defineTheme(MONACO_THEME_NAMES.light, {
    base: 'vs',
    inherit: true,
    rules: [
      { token: 'comment', foreground: '94A3B8' },
      { token: 'keyword', foreground: '7C3AED' },
      { token: 'string', foreground: '0F766E' },
      { token: 'number', foreground: 'C2410C' },
      { token: 'tag', foreground: '2563EB' },
    ],
    colors: {
      'editor.background': '#FFFFFF',
      'editor.foreground': '#0F172A',
      'editor.lineHighlightBackground': '#F8FAFC',
      'editorLineNumber.foreground': '#94A3B8',
      'editorLineNumber.activeForeground': '#475569',
      'editorCursor.foreground': '#4F46E5',
      'editor.selectionBackground': '#C7D2FE99',
      'editor.inactiveSelectionBackground': '#E2E8F099',
      'editorWhitespace.foreground': '#CBD5E1',
      'editorIndentGuide.background1': '#E2E8F0',
      'editorIndentGuide.activeBackground1': '#CBD5E1',
    },
  })
}

/**
 * 返回编辑器默认配置，避免页面层重复拼装基础 option。
 */
export function getDefaultEditorOptions(): monaco.editor.IStandaloneEditorConstructionOptions {
  return {
    automaticLayout: true,
    contextmenu: true,
    fontSize: 14,
    fontFamily: 'Consolas, Monaco, "Courier New", monospace',
    fontLigatures: true,
    lineHeight: 22,
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    smoothScrolling: true,
    tabSize: 2,
    insertSpaces: true,
    wordWrap: 'on',
    padding: { top: 16, bottom: 16 },
    quickSuggestions: {
      comments: false,
      other: true,
      strings: true,
    },
    suggestOnTriggerCharacters: true,
    fixedOverflowWidgets: true,
  }
}

/**
 * 将业务主题模式映射为 Monaco 主题名称。
 */
export function resolveMonacoTheme(mode: EditorThemeMode) {
  return MONACO_THEME_NAMES[mode] ?? MONACO_THEME_NAMES.dark
}

/**
 * 将业务语言标识映射为 Monaco 可识别的语言。
 */
export function resolveMonacoLanguage(language: EditorLanguage) {
  return LANGUAGE_ALIASES[language] ?? 'plaintext'
}

/**
 * 返回编辑器默认主题名称，页面层可按需覆盖。
 */
export function getDefaultEditorTheme() {
  return 'dark' as const
}

/**
 * 生成当前语言的默认补全项，并合并调用方传入的自定义补全。
 */
export function resolveCompletionSuggestions(
  language: EditorLanguage,
  completionConfig?: MonacoCompletionConfig,
) {
  if (completionConfig?.enabled === false) {
    return [] as MonacoCompletionSuggestion[]
  }

  const suggestions: MonacoCompletionSuggestion[] = []
  if (completionConfig?.includeDefault !== false) {
    suggestions.push(...getDefaultCompletionSuggestions(language))
  }

  if (completionConfig?.suggestions?.length) {
    suggestions.push(
      ...completionConfig.suggestions.filter(
        suggestion => !suggestion.languages || suggestion.languages.includes(language),
      ),
    )
  }

  return suggestions
}

/**
 * 将业务补全项转换为 Monaco 所需的结构。
 */
export function toMonacoCompletionItems(
  suggestions: MonacoCompletionSuggestion[],
  range: monaco.IRange,
): monaco.languages.CompletionItem[] {
  return suggestions.map((suggestion, index) => ({
    label: suggestion.label,
    insertText: suggestion.insertText,
    detail: suggestion.detail,
    documentation: suggestion.documentation,
    filterText: suggestion.filterText ?? suggestion.label,
    sortText: suggestion.sortText ?? `${index}`.padStart(4, '0'),
    kind: resolveCompletionKind(suggestion.kind),
    range,
    insertTextRules:
      suggestion.insertTextRules === 'snippet'
        ? monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet
        : monaco.languages.CompletionItemInsertTextRule.None,
  }))
}

/**
 * 返回未来可被外部复用的快捷键枚举，避免页面层依赖 Monaco 深路径。
 */
export const MonacoKeyMod = monaco.KeyMod
export const MonacoKeyCode = monaco.KeyCode

/**
 * 根据语言给出最小可用的默认片段补全。
 */
function getDefaultCompletionSuggestions(language: EditorLanguage) {
  if (language === 'vue') {
    return [
      {
        label: 'vue-sfc',
        insertText: [
          '<template>',
          '  <section class="$1">',
          '    $2',
          '  </section>',
          '</template>',
          '',
          '<script setup lang="ts">',
          '$3',
          '</script>',
          '',
          '<style scoped>',
          '$4',
          '</style>',
        ].join('\n'),
        detail: 'Vue 单文件组件模板',
        documentation: '快速插入一个包含 template、script setup 和 style scoped 的页面骨架。',
        kind: 'Snippet',
        insertTextRules: 'snippet',
      },
      {
        label: 'script-setup',
        insertText: ['<script setup lang="ts">', "const title = '$1'", '</script>'].join('\n'),
        detail: 'script setup 片段',
        documentation: '插入 Vue 3 script setup 基础代码块。',
        kind: 'Snippet',
        insertTextRules: 'snippet',
      },
      {
        label: 'scoped-style',
        insertText: ['<style scoped>', '.$1 {', '  $2', '}', '</style>'].join('\n'),
        detail: 'scoped 样式块',
        documentation: '插入带 `scoped` 的样式代码块。',
        kind: 'Snippet',
        insertTextRules: 'snippet',
      },
      {
        label: 'page-meta',
        insertText: [
          'const pageMeta = {',
          "  title: '$1',",
          "  summary: '$2',",
          '}',
        ].join('\n'),
        detail: '页面元信息对象',
        documentation: '插入一段通用的页面元信息结构，便于后续扩展业务 DSL。',
        kind: 'Snippet',
        insertTextRules: 'snippet',
      },
    ] satisfies MonacoCompletionSuggestion[]
  }

  if (language === 'json') {
    return [
      {
        label: 'page-json',
        insertText: ['{', '  "title": "$1",', '  "summary": "$2"', '}'].join('\n'),
        detail: '页面 JSON 片段',
        documentation: '插入一个最小的 JSON 结构。',
        kind: 'Snippet',
        insertTextRules: 'snippet',
      },
    ] satisfies MonacoCompletionSuggestion[]
  }

  if (language === 'typescript' || language === 'javascript') {
    return [
      {
        label: 'const-block',
        insertText: "const $1 = '$2'",
        detail: '常量定义',
        documentation: '插入一个基础常量定义片段。',
        kind: 'Snippet',
        insertTextRules: 'snippet',
      },
    ] satisfies MonacoCompletionSuggestion[]
  }

  return [] as MonacoCompletionSuggestion[]
}

/**
 * 将业务补全种类映射为 Monaco 内置枚举。
 */
function resolveCompletionKind(kind: MonacoCompletionKind = 'Snippet') {
  if (kind === 'Keyword') return monaco.languages.CompletionItemKind.Keyword
  if (kind === 'Function') return monaco.languages.CompletionItemKind.Function
  if (kind === 'Property') return monaco.languages.CompletionItemKind.Property
  if (kind === 'Text') return monaco.languages.CompletionItemKind.Text
  return monaco.languages.CompletionItemKind.Snippet
}

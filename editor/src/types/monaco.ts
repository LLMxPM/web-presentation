/**
 * 文件功能：定义 Monaco 编辑器组件的公共类型，供组件、页面与测试统一复用。
 */
import type * as Monaco from 'monaco-editor'

export type EditorLanguage =
  | 'vue'
  | 'html'
  | 'javascript'
  | 'typescript'
  | 'json'
  | 'yaml'
  | 'plaintext'
  | 'css'

export type EditorSaveReason = 'manual' | 'auto'
export type EditorThemeMode = 'dark' | 'light'

export type MonacoCompletionKind = 'Snippet' | 'Keyword' | 'Function' | 'Property' | 'Text'

export interface MonacoCompletionSuggestion {
  label: string
  insertText: string
  detail?: string
  documentation?: string
  kind?: MonacoCompletionKind
  insertTextRules?: 'snippet' | 'text'
  sortText?: string
  filterText?: string
  languages?: EditorLanguage[]
}

export interface MonacoCompletionConfig {
  enabled?: boolean
  includeDefault?: boolean
  suggestions?: MonacoCompletionSuggestion[]
}

export interface MonacoShortcutBinding {
  id: string
  keybinding: number
}

export interface MonacoEditorExpose {
  focus: () => void
  markClean: (baselineValue?: string) => void
  triggerSave: (reason?: EditorSaveReason) => void
  getValue: () => string
}

export interface MonacoEditorReadyPayload extends MonacoEditorExpose {
  editor: Monaco.editor.IStandaloneCodeEditor
  monaco: typeof Monaco
}

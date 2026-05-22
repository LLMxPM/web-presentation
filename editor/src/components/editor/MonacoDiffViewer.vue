<!-- 文件功能：封装只读 Monaco DiffEditor，支持内联展示两个文本版本之间的差异。 -->
<template>
  <div class="monaco-diff-viewer relative w-full h-full">
    <div ref="containerRef" class="w-full" :style="containerStyle"></div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, shallowRef, watch } from 'vue'

import type * as Monaco from 'monaco-editor'

import type { EditorLanguage, EditorThemeMode } from '@/types/monaco'
import {
  getDefaultEditorTheme,
  getDefaultEditorOptions,
  initializeMonaco,
  resolveMonacoLanguage,
  resolveMonacoTheme,
} from '@/utils/monaco'

const props = withDefaults(defineProps<{
  originalValue: string
  modifiedValue: string
  language?: EditorLanguage
  height?: string | number
  theme?: EditorThemeMode
}>(), {
  language: 'vue',
  height: 420,
  theme: getDefaultEditorTheme(),
})

const containerRef = shallowRef<HTMLDivElement | null>(null)
const monacoRef = shallowRef<typeof Monaco | null>(null)
const diffEditorRef = shallowRef<Monaco.editor.IStandaloneDiffEditor | null>(null)
const originalModelRef = shallowRef<Monaco.editor.ITextModel | null>(null)
const modifiedModelRef = shallowRef<Monaco.editor.ITextModel | null>(null)

let modelSeed = 0
const diffViewerInstanceId = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`

const containerStyle = computed(() => ({
  height: typeof props.height === 'number' ? `${props.height}px` : props.height,
}))

/**
 * 为 diff 两侧构建独立 model，避免组件实例之间共享内容。
 */
function createModel(monacoInstance: typeof Monaco, value: string, suffix: 'original' | 'modified') {
  modelSeed += 1
  const extension = props.language === 'json' ? 'json' : props.language === 'css' ? 'css' : 'txt'
  return monacoInstance.editor.createModel(
    value,
    resolveMonacoLanguage(props.language),
    monacoInstance.Uri.parse(`inmemory://page-diff/${diffViewerInstanceId}-${suffix}-${modelSeed}.${extension}`),
  )
}

/**
 * 同步 diff 两侧文本内容，供版本切换时复用。
 */
function syncModels() {
  if (!originalModelRef.value || !modifiedModelRef.value) return
  if (originalModelRef.value.getValue() !== props.originalValue) {
    originalModelRef.value.setValue(props.originalValue)
  }
  if (modifiedModelRef.value.getValue() !== props.modifiedValue) {
    modifiedModelRef.value.setValue(props.modifiedValue)
  }
}

onMounted(async () => {
  if (!containerRef.value) return

  const monacoInstance = await initializeMonaco()
  monacoRef.value = monacoInstance
  originalModelRef.value = createModel(monacoInstance, props.originalValue, 'original')
  modifiedModelRef.value = createModel(monacoInstance, props.modifiedValue, 'modified')

  diffEditorRef.value = monacoInstance.editor.createDiffEditor(containerRef.value, {
    ...getDefaultEditorOptions(),
    theme: resolveMonacoTheme(props.theme),
    readOnly: true,
    originalEditable: false,
    // Monaco 官方提供的紧凑 inline diff 模式会隐藏原始侧行号，并尽量以内联方式呈现删除内容。
    compactMode: true,
    experimental: {
      useTrueInlineView: true,
    },
    lineNumbers: 'on',
    lineNumbersMinChars: 3,
    renderSideBySide: false,
    enableSplitViewResizing: false,
    minimap: { enabled: false },
    diffWordWrap: 'on',
    glyphMargin: false,
    lineDecorationsWidth: 8,
    renderOverviewRuler: true,
  })

  diffEditorRef.value.setModel({
    original: originalModelRef.value,
    modified: modifiedModelRef.value,
  })
})

watch(() => [props.originalValue, props.modifiedValue], () => {
  syncModels()
})

watch(() => props.language, (language) => {
  if (!monacoRef.value || !originalModelRef.value || !modifiedModelRef.value) return
  const nextLanguage = resolveMonacoLanguage(language)
  monacoRef.value.editor.setModelLanguage(originalModelRef.value, nextLanguage)
  monacoRef.value.editor.setModelLanguage(modifiedModelRef.value, nextLanguage)
})

watch(() => props.theme, (theme) => {
  monacoRef.value?.editor.setTheme(resolveMonacoTheme(theme))
})

onBeforeUnmount(() => {
  diffEditorRef.value?.dispose()
  diffEditorRef.value = null
  originalModelRef.value?.dispose()
  originalModelRef.value = null
  modifiedModelRef.value?.dispose()
  modifiedModelRef.value = null
})
</script>

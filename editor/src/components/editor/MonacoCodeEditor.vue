<!-- 文件功能：封装可复用的 Monaco 编辑器组件，统一提供语言、自动保存、快捷键与补全能力。 -->
<template>
  <div class="monaco-code-editor relative w-full h-full">
    <div ref="containerRef" class="w-full" :style="containerStyle"></div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, shallowRef, watch } from 'vue'

import type * as Monaco from 'monaco-editor'

import type {
  EditorLanguage,
  EditorSaveReason,
  EditorThemeMode,
  MonacoCompletionConfig,
  MonacoEditorExpose,
  MonacoEditorReadyPayload,
  MonacoShortcutBinding,
} from '@/types/monaco'
import {
  MonacoKeyCode,
  MonacoKeyMod,
  getDefaultEditorOptions,
  getDefaultEditorTheme,
  initializeMonaco,
  resolveCompletionSuggestions,
  resolveMonacoLanguage,
  resolveMonacoTheme,
  toMonacoCompletionItems,
} from '@/utils/monaco'

const props = withDefaults(defineProps<{
  modelValue: string
  language?: EditorLanguage
  readonly?: boolean
  height?: string | number
  theme?: EditorThemeMode
  autoSaveDelay?: number | null
  shortcutBindings?: MonacoShortcutBinding[]
  completionConfig?: MonacoCompletionConfig
}>(), {
  language: 'vue',
  readonly: false,
  height: 480,
  theme: getDefaultEditorTheme(),
  autoSaveDelay: 5000,
  shortcutBindings: () => [],
  completionConfig: () => ({ includeDefault: true }),
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  save: [{ reason: EditorSaveReason; value: string }]
  shortcut: [id: string]
  ready: [payload: MonacoEditorReadyPayload]
  'dirty-change': [dirty: boolean]
}>()

const containerRef = shallowRef<HTMLDivElement | null>(null)
const monacoRef = shallowRef<typeof Monaco | null>(null)
const editorRef = shallowRef<Monaco.editor.IStandaloneCodeEditor | null>(null)
const modelRef = shallowRef<Monaco.editor.ITextModel | null>(null)
const completionDisposableRef = shallowRef<Monaco.IDisposable | null>(null)
const shortcutDisposablesRef = shallowRef<Monaco.IDisposable[]>([])

let autoSaveTimer: ReturnType<typeof setTimeout> | null = null
let ignoreNextModelValueSync = false
let suppressModelChangeEvent = false
let baselineValue = props.modelValue
let isDirty = false
let modelSeed = 0
const editorInstanceId = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`

const containerStyle = computed(() => ({
  height: typeof props.height === 'number' ? `${props.height}px` : props.height,
}))

/**
 * 更新脏状态并向父层同步，避免页面重复维护对比逻辑。
 */
function updateDirty(nextDirty: boolean) {
  if (isDirty === nextDirty) return
  isDirty = nextDirty
  emit('dirty-change', nextDirty)
}

/**
 * 停止尚未触发的自动保存任务。
 */
function clearAutoSaveTimer() {
  if (!autoSaveTimer) return
  clearTimeout(autoSaveTimer)
  autoSaveTimer = null
}

/**
 * 返回当前编辑器中的最新文本内容。
 */
function getValue() {
  return editorRef.value?.getValue() ?? props.modelValue
}

/**
 * 触发保存事件，由页面层决定如何持久化。
 */
function triggerSave(reason: EditorSaveReason = 'manual') {
  if (props.readonly) return
  emit('save', { reason, value: getValue() })
}

/**
 * 将当前内容标记为已保存基线，供页面保存成功后调用。
 */
function markClean(nextBaselineValue = getValue()) {
  baselineValue = nextBaselineValue
  clearAutoSaveTimer()
  updateDirty(false)
}

/**
 * 为后续更多功能页暴露聚焦和状态控制能力。
 */
function focus() {
  editorRef.value?.focus()
}

/**
 * 根据当前配置注册补全提供器，并确保只对当前 model 生效。
 */
function registerCompletionProvider() {
  completionDisposableRef.value?.dispose()
  completionDisposableRef.value = null

  if (!monacoRef.value || !modelRef.value) return

  const suggestions = resolveCompletionSuggestions(props.language, props.completionConfig)
  if (suggestions.length === 0) return

  const monacoLanguage = resolveMonacoLanguage(props.language)
  const targetUri = modelRef.value.uri.toString()
  completionDisposableRef.value = monacoRef.value.languages.registerCompletionItemProvider(monacoLanguage, {
    provideCompletionItems(model: Monaco.editor.ITextModel, position: Monaco.Position) {
      if (model.uri.toString() !== targetUri) {
        return { suggestions: [] }
      }

      const wordUntilPosition = model.getWordUntilPosition(position)
      const range = {
        startLineNumber: position.lineNumber,
        endLineNumber: position.lineNumber,
        startColumn: wordUntilPosition.startColumn,
        endColumn: wordUntilPosition.endColumn,
      }

      return {
        suggestions: toMonacoCompletionItems(suggestions, range),
      }
    },
  })
}

/**
 * 注册内置和调用方自定义的快捷键监听。
 */
function registerShortcuts() {
  if (!editorRef.value) return

  shortcutDisposablesRef.value.forEach(disposable => disposable.dispose())
  shortcutDisposablesRef.value = []

  shortcutDisposablesRef.value.push(
    editorRef.value.addAction({
      id: 'page-code-save',
      label: '保存',
      keybindings: [MonacoKeyMod.CtrlCmd | MonacoKeyCode.KeyS],
      run: () => {
        triggerSave('manual')
      },
    }),
  )

  props.shortcutBindings.forEach(binding => {
    const disposable = editorRef.value?.addAction({
      id: `page-code-shortcut-${binding.id}`,
      label: binding.id,
      keybindings: [binding.keybinding],
      run: () => {
        emit('shortcut', binding.id)
      },
    })

    if (disposable) {
      shortcutDisposablesRef.value.push(disposable)
    }
  })
}

/**
 * 内容变化后调度自动保存，仅在脏状态下触发。
 */
function scheduleAutoSave() {
  clearAutoSaveTimer()

  if (props.readonly || !isDirty || !props.autoSaveDelay || props.autoSaveDelay <= 0) {
    return
  }

  autoSaveTimer = setTimeout(() => {
    triggerSave('auto')
  }, props.autoSaveDelay)
}

/**
 * 处理编辑器内部输入，并同步给页面层。
 */
function handleModelContentChange() {
  if (suppressModelChangeEvent) {
    suppressModelChangeEvent = false
    return
  }

  const nextValue = getValue()
  ignoreNextModelValueSync = true
  emit('update:modelValue', nextValue)
  updateDirty(nextValue !== baselineValue)
  scheduleAutoSave()
}

/**
 * 构建唯一 model，避免不同编辑器实例共享状态。
 */
function createModel(monacoInstance: typeof Monaco, initialValue: string) {
  modelSeed += 1
  const extension = props.language === 'json' ? 'json' : props.language === 'css' ? 'css' : 'txt'
  return monacoInstance.editor.createModel(
    initialValue,
    resolveMonacoLanguage(props.language),
    monacoInstance.Uri.parse(`inmemory://page-code/${editorInstanceId}-${modelSeed}.${extension}`),
  )
}

onMounted(async () => {
  if (!containerRef.value) return

  const monacoInstance = await initializeMonaco()
  monacoRef.value = monacoInstance
  modelRef.value = createModel(monacoInstance, props.modelValue)

  editorRef.value = monacoInstance.editor.create(containerRef.value, {
    ...getDefaultEditorOptions(),
    model: modelRef.value,
    readOnly: props.readonly,
    theme: resolveMonacoTheme(props.theme),
  })

  editorRef.value.onDidChangeModelContent(() => {
    handleModelContentChange()
  })

  registerShortcuts()
  registerCompletionProvider()

  const readyPayload: MonacoEditorReadyPayload = {
    editor: editorRef.value,
    monaco: monacoInstance,
    focus,
    markClean,
    triggerSave,
    getValue,
  }
  emit('ready', readyPayload)
})

watch(() => props.modelValue, (nextValue) => {
  if (!editorRef.value || !modelRef.value) return

  if (ignoreNextModelValueSync) {
    ignoreNextModelValueSync = false
    return
  }

  if (editorRef.value.getValue() === nextValue) {
    return
  }

  suppressModelChangeEvent = true
  modelRef.value.setValue(nextValue)
  baselineValue = nextValue
  clearAutoSaveTimer()
  updateDirty(false)
})

watch(() => props.language, (nextLanguage) => {
  if (!monacoRef.value || !modelRef.value) return

  monacoRef.value.editor.setModelLanguage(modelRef.value, resolveMonacoLanguage(nextLanguage))
  registerCompletionProvider()
})

watch(() => props.readonly, (readonly) => {
  editorRef.value?.updateOptions({ readOnly: readonly })
  if (readonly) {
    clearAutoSaveTimer()
  }
})

watch(() => props.theme, (theme) => {
  monacoRef.value?.editor.setTheme(resolveMonacoTheme(theme))
})

watch(() => props.autoSaveDelay, () => {
  scheduleAutoSave()
})

watch(() => props.shortcutBindings, () => {
  registerShortcuts()
}, { deep: true })

watch(() => props.completionConfig, () => {
  registerCompletionProvider()
}, { deep: true })

onBeforeUnmount(() => {
  clearAutoSaveTimer()
  completionDisposableRef.value?.dispose()
  completionDisposableRef.value = null
  shortcutDisposablesRef.value.forEach(disposable => disposable.dispose())
  shortcutDisposablesRef.value = []
  editorRef.value?.dispose()
  editorRef.value = null
  modelRef.value?.dispose()
  modelRef.value = null
})

defineExpose<MonacoEditorExpose>({
  focus,
  markClean,
  triggerSave,
  getValue,
})
</script>

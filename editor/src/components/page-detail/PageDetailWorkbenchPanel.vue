<!-- 文件功能：承载页面详情页的代码编辑主工作区，负责编辑器主题、自动保存和 Monaco 事件转发。 -->
<template>
  <section
    class="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl shadow-sm ring-1 transition-all duration-300"
    :class="themeClasses.card">
    <div class="flex items-center justify-between gap-4 border-b px-6 py-4 transition-colors duration-300 flex-wrap"
      :class="themeClasses.header">
      <div class="inline-flex items-center gap-2 text-sm font-semibold" :class="themeClasses.text">
        <Code2 class="h-4 w-4" />
        代码编辑器
      </div>

      <div class="flex items-center gap-5 flex-wrap">
        <div class="flex items-center gap-3">
          <button
            type="button"
            class="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-semibold transition-all duration-200"
            :class="themeClasses.toolbarButton"
            @click="emit('copy-code')"
          >
            <Copy class="h-3.5 w-3.5" />
            复制代码
          </button>

          <div class="h-4 w-px transition-colors duration-300" :class="themeClasses.toolbarDivider"></div>

          <div class="flex items-center rounded-lg p-0.5 transition-colors duration-300"
            :class="themeClasses.switchContainer">
            <button type="button" title="明亮模式"
              class="flex h-6 w-6 items-center justify-center rounded-md transition-all duration-200"
              :class="props.editorTheme === 'light' ? themeClasses.switchActive : themeClasses.switchInactive"
              @click="updateEditorTheme('light')">
              <Sun class="h-3.5 w-3.5" />
            </button>
            <button type="button" title="暗黑模式"
              class="flex h-6 w-6 items-center justify-center rounded-md transition-all duration-200"
              :class="props.editorTheme === 'dark' ? themeClasses.switchActive : themeClasses.switchInactive"
              @click="updateEditorTheme('dark')">
              <Moon class="h-3.5 w-3.5" />
            </button>
          </div>

          <div class="h-4 w-px transition-colors duration-300" :class="themeClasses.toolbarDivider"></div>

          <div class="flex items-center gap-2">
            <span class="select-none whitespace-nowrap text-[12px] font-extrabold uppercase tracking-widest opacity-50"
              :class="themeClasses.text">
              自动保存
            </span>
            <div class="relative group outline-none" tabindex="0" @blur="isAutoSaveMenuOpen = false">
              <div
                class="flex min-w-[72px] cursor-pointer items-center rounded-md pl-2.5 pr-6 py-1 text-[11px] font-bold tracking-tight transition-all"
                :class="[themeClasses.text, themeClasses.selectBox]" @click="isAutoSaveMenuOpen = !isAutoSaveMenuOpen">
                <span>{{ currentAutoSaveLabel }}</span>
                <div
                  class="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 opacity-40 transition-all duration-200 group-hover:opacity-100"
                  :class="[themeClasses.text, { 'rotate-180': isAutoSaveMenuOpen }]">
                  <ChevronDown class="h-3 w-3" />
                </div>
              </div>

              <transition enter-active-class="transition duration-100 ease-out"
                enter-from-class="transform scale-95 opacity-0" enter-to-class="transform scale-100 opacity-100"
                leave-active-class="transition duration-75 ease-in" leave-from-class="transform scale-100 opacity-100"
                leave-to-class="transform scale-95 opacity-0">
                <div v-show="isAutoSaveMenuOpen"
                  class="absolute left-1/2 top-full z-20 mt-1.5 min-w-[92px] -translate-x-1/2 overflow-hidden rounded-lg border origin-top"
                  :class="themeClasses.dropdownMenu">
                  <div v-for="option in props.autoSaveOptions" :key="option.value"
                    class="px-3 py-1.5 text-center text-[11px] transition-colors cursor-pointer"
                    :class="props.autoSaveDelay === option.value ? themeClasses.dropdownItemActive : themeClasses.dropdownItem"
                    @mousedown.prevent="selectAutoSaveValue(option.value)">
                    {{ option.label }}
                  </div>
                </div>
              </transition>
            </div>
          </div>
        </div>
      </div>

    </div>

    <div class="min-h-0 flex-1 transition-colors duration-300"
      :class="themeClasses.editor">
      <MonacoCodeEditor :model-value="props.modelValue" :language="props.editorLanguage" :theme="props.editorTheme"
        :auto-save-delay="props.autoSaveDelay" :completion-config="{ includeDefault: true }"
        :height="props.editorHeight" @update:model-value="emit('update:modelValue', $event)"
        @save="emit('save', $event)" @ready="emit('ready', $event)" @dirty-change="emit('dirty-change', $event)" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ChevronDown, Code2, Copy, Moon, Sun } from '@lucide/vue'

import MonacoCodeEditor from '@/components/editor/MonacoCodeEditor.vue'
import type {
  EditorLanguage,
  EditorSaveReason,
  EditorThemeMode,
  MonacoEditorReadyPayload,
} from '@/types/monaco'

type WorkbenchPane = 'editor' | 'assistant'

interface AutoSaveOption {
  label: string
  value: number
}

interface Props {
  workspaceId: number
  projectId: number
  pageId: number
  pageTitle: string
  activePane: WorkbenchPane
  modelValue: string
  editorLanguage: EditorLanguage
  editorTheme: EditorThemeMode
  autoSaveDelay: number
  autoSaveOptions: AutoSaveOption[]
  editorHeight: string | number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:activePane': [value: WorkbenchPane]
  'update:modelValue': [value: string]
  'update:editorTheme': [value: EditorThemeMode]
  'update:autoSaveDelay': [value: number]
  save: [{ reason: EditorSaveReason; value: string }]
  ready: [payload: MonacoEditorReadyPayload]
  'dirty-change': [dirty: boolean]
  'copy-code': []
  'apply-suggested-content': [content: string]
  'page-updated': []
}>()

const isAutoSaveMenuOpen = ref(false)
const currentAutoSaveLabel = computed(() => (
  props.autoSaveOptions.find(option => option.value === props.autoSaveDelay)?.label ?? '未知'
))

const themeClasses = computed(() => {
  if (props.editorTheme === 'dark') {
    return {
      card: 'bg-slate-900 ring-white/10',
      header: 'bg-slate-800 border-white/5',
      editor: 'bg-slate-950',
      text: 'text-slate-100',
      mutedText: 'text-slate-400',
      switchContainer: 'bg-black/20',
      switchActive: 'bg-white/10 text-white shadow-sm font-bold',
      switchInactive: 'text-slate-500 hover:text-slate-300 hover:bg-white/5',
      toolbarDivider: 'bg-white/10',
      toolbarButton: 'text-slate-300 hover:bg-white/5 hover:text-white',
      selectBox: 'bg-transparent border border-transparent hover:bg-white/5 focus:ring-1 focus:ring-white/20',
      dropdownMenu: 'bg-slate-800 border-slate-700/80 ring-1 ring-white/5 shadow-xl',
      dropdownItem: 'text-slate-300 hover:bg-slate-700/50 hover:text-white',
      dropdownItemActive: 'text-indigo-400 bg-indigo-500/10 font-bold',
      tabContainer: 'bg-black/20',
      tabActive: 'bg-white/10 text-white shadow-sm',
      tabInactive: 'text-slate-400 hover:bg-white/5 hover:text-slate-200',
    }
  }

  return {
    card: 'border border-slate-200 bg-white ring-slate-200',
    header: 'border-slate-200 bg-slate-50',
    editor: 'bg-white',
    text: 'text-slate-900',
    mutedText: 'text-slate-500',
    switchContainer: 'bg-slate-200/50',
    switchActive: 'bg-white text-indigo-600 shadow-sm font-bold',
    switchInactive: 'text-slate-400 hover:text-slate-600 hover:bg-black/5',
    toolbarDivider: 'bg-black/5',
    toolbarButton: 'text-slate-600 hover:bg-slate-200/70 hover:text-slate-900',
    selectBox: 'bg-transparent border border-transparent hover:bg-slate-200/50 focus:ring-1 focus:ring-black/10',
    dropdownMenu: 'bg-white border-slate-200 ring-1 ring-slate-900/5 shadow-lg',
    dropdownItem: 'text-slate-600 hover:bg-slate-100/80 hover:text-slate-900',
    dropdownItemActive: 'text-indigo-600 bg-indigo-50 font-bold',
    tabContainer: 'bg-slate-200/60',
    tabActive: 'bg-white text-slate-900 shadow-sm',
    tabInactive: 'text-slate-500 hover:bg-white/70 hover:text-slate-800',
  }
})

/**
 * 切换编辑器主题，由父层统一维护主题状态。
 * @param nextTheme 目标主题
 */
function updateEditorTheme(nextTheme: EditorThemeMode): void {
  emit('update:editorTheme', nextTheme)
}

/**
 * 选择自动保存延迟，并在选择后立即关闭下拉菜单。
 * @param value 自动保存延迟毫秒数
 */
function selectAutoSaveValue(value: number): void {
  emit('update:autoSaveDelay', value)
  isAutoSaveMenuOpen.value = false
}
</script>

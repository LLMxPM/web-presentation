<!-- 文件功能：渲染智能体会话新建按钮与会话切换下拉菜单。 -->
<template>
  <div class="relative flex items-center gap-2" v-click-outside="() => $emit('close')">
    <div class="inline-flex h-8 overflow-hidden rounded-xl border border-slate-200 bg-slate-50/80 shadow-sm">
      <BaseButton
        variant="ghost"
        size="sm"
        custom-class="h-8 rounded-none border-0 px-3 py-0 text-xs font-semibold shadow-none"
        :disabled="createDisabled"
        @click="$emit('create')"
      >
        <Plus class="h-3.5 w-3.5" />
        新会话
      </BaseButton>
      <button
        type="button"
        class="inline-flex w-9 items-center justify-center border-l border-slate-200 text-slate-500 transition hover:bg-white hover:text-slate-700"
        :disabled="switchDisabled"
        aria-label="切换会话"
        title="切换会话"
        @click.stop="$emit('toggle')"
      >
        <ChevronDown class="h-4 w-4 transition-transform duration-200" :class="{ 'rotate-180': menuVisible }" />
      </button>
    </div>

    <Transition name="fade-scale">
      <div
        v-if="menuVisible"
        class="absolute top-full z-30 mt-2 w-[320px] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl"
        :class="align === 'right' ? 'right-0' : 'left-0'"
      >
        <div class="border-b border-slate-100 px-4 py-3">
          <div class="flex items-center justify-between gap-3">
            <p class="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">会话切换</p>
            <span class="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500">
              {{ sessionCountText }}
            </span>
          </div>
          <label v-if="totalSessionCount > 0" class="relative mt-3 block">
            <Search class="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
            <input
              v-model="searchKeyword"
              type="search"
              aria-label="搜索会话标题"
              placeholder="搜索会话标题"
              class="h-8 w-full rounded-lg border border-slate-200 bg-slate-50 pl-8 pr-8 text-xs font-medium text-slate-700 outline-none transition placeholder:text-slate-400 focus:border-sky-300 focus:bg-white focus:ring-2 focus:ring-sky-100"
              @click.stop
            >
            <button
              v-if="normalizedSearchKeyword"
              type="button"
              class="absolute right-1.5 top-1/2 flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded-md text-slate-400 transition hover:bg-slate-200 hover:text-slate-600"
              aria-label="清空会话搜索"
              title="清空会话搜索"
              @click.stop="clearSearch"
            >
              <X class="h-3.5 w-3.5" />
            </button>
          </label>
        </div>

        <div v-if="isFetching && !totalSessionCount" class="px-4 py-6 text-center text-sm text-slate-400">
          正在读取智能体会话...
        </div>
        <div v-else-if="visibleSessions.length" class="max-h-[360px] overflow-y-auto p-2">
          <button
            v-for="session in visibleSessions"
            :key="session.session_id"
            type="button"
            class="mb-1.5 flex w-full items-start justify-between gap-3 rounded-xl border px-3 py-3 text-left transition last:mb-0"
            :class="session.session_id === activeSessionId
              ? 'border-sky-200 bg-sky-50 text-sky-700'
              : 'border-transparent text-slate-600 hover:border-slate-200 hover:bg-slate-50 hover:text-slate-800'"
            @click="$emit('switch-session', session.session_id)"
          >
            <div class="min-w-0 flex-1">
              <div class="flex min-w-0 items-center gap-2">
                <p class="min-w-0 flex-1 truncate text-sm font-semibold">{{ resolveSessionDisplayName(session) }}</p>
                <span class="shrink-0 text-[10px] opacity-50">{{ resolveSessionSubtitle(session) }}</span>
              </div>
              <p class="mt-1 truncate text-[11px] opacity-70" :title="resolveSessionScopePath(session)">
                {{ resolveSessionScopePath(session) }}
              </p>
              <p v-if="resolveSessionModelLabel(session)" class="mt-1 truncate text-[11px] opacity-70"
                :title="resolveSessionModelLabel(session)">
                {{ resolveSessionModelLabel(session) }}
              </p>
            </div>
            <div class="flex shrink-0 flex-col items-end gap-1">
              <span
                v-if="getSessionRunBadge(session.session_id)"
                class="rounded-full border px-2 py-0.5 text-[10px] font-semibold"
                :class="getSessionRunBadge(session.session_id)?.className"
              >
                {{ getSessionRunBadge(session.session_id)?.label }}
              </span>
              <Check v-if="session.session_id === activeSessionId" class="mt-0.5 h-4 w-4" />
            </div>
          </button>
        </div>
        <div v-else-if="normalizedSearchKeyword" class="px-4 py-6 text-center text-sm text-slate-400">
          没有匹配的会话标题。
        </div>
        <div v-else class="px-4 py-6 text-center text-sm text-slate-400">
          当前范围还没有智能体会话，发送第一条消息后会自动创建。
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, ChevronDown, Plus, Search, X } from '@lucide/vue'

import BaseButton from '@/components/ui/BaseButton.vue'
import {
  resolveSessionDisplayName,
  resolveSessionModelLabel,
  resolveSessionScopePath,
  resolveSessionSubtitle,
} from '@/components/agent/agent-session-scope'
import type { AgentSessionItem } from '@/types/api'

const MAX_VISIBLE_SESSIONS = 50

const props = defineProps<{
  sessions: AgentSessionItem[] | undefined
  activeSessionId: string
  activeSessionLabel: string
  isFetching: boolean
  menuVisible: boolean
  createDisabled: boolean
  switchDisabled: boolean
  align: 'left' | 'right'
  getSessionRunBadge: (sessionId: string) => { label: string, className: string } | null
}>()

defineEmits<{
  create: []
  toggle: []
  close: []
  'switch-session': [sessionId: string]
}>()

const searchKeyword = ref('')
const normalizedSearchKeyword = computed(() => normalizeSearchText(searchKeyword.value.trim()))
const totalSessionCount = computed(() => props.sessions?.length ?? 0)
const recentSessions = computed(() => [...(props.sessions ?? [])].sort(compareSessionRecentFirst))
const filteredSessions = computed(() => {
  if (!normalizedSearchKeyword.value) {
    return recentSessions.value
  }
  return recentSessions.value.filter(session => (
    normalizeSearchText(resolveSessionDisplayName(session)).includes(normalizedSearchKeyword.value)
  ))
})
const visibleSessions = computed(() => filteredSessions.value.slice(0, MAX_VISIBLE_SESSIONS))
const sessionCountText = computed(() => {
  const total = totalSessionCount.value
  if (!total) {
    return '0 个'
  }
  if (normalizedSearchKeyword.value) {
    return `匹配 ${filteredSessions.value.length} 个`
  }
  if (total > MAX_VISIBLE_SESSIONS) {
    return `最近 ${MAX_VISIBLE_SESSIONS} / 共 ${total}`
  }
  return `共 ${total} 个`
})

watch(
  () => props.menuVisible,
  (visible) => {
    if (!visible) {
      searchKeyword.value = ''
    }
  },
)

/**
 * 清空本地标题搜索关键字。
 */
function clearSearch() {
  searchKeyword.value = ''
}

/**
 * 会话列表按最近更新时间降序展示，缺失时间的会话自然排到后面。
 */
function compareSessionRecentFirst(left: AgentSessionItem, right: AgentSessionItem): number {
  return resolveSessionTime(right) - resolveSessionTime(left)
}

/**
 * 解析会话更新时间戳，供最近 50 条限制稳定生效。
 */
function resolveSessionTime(session: AgentSessionItem): number {
  const value = session.updated_at || session.created_at || ''
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) ? timestamp : 0
}

/**
 * 标题搜索统一大小写，中文标题保持原样参与 includes 匹配。
 */
function normalizeSearchText(value: string): string {
  return value.toLocaleLowerCase()
}

const vClickOutside = {
  mounted(el: HTMLElement, binding: { value: () => void }) {
    const clickOutsideEvent = (event: Event) => {
      const target = event.target as Node | null
      if (target && !el.contains(target)) {
        binding.value()
      }
    }
      ; (el as HTMLElement & { clickOutsideEvent?: (event: Event) => void }).clickOutsideEvent = clickOutsideEvent
    document.body.addEventListener('click', clickOutsideEvent)
  },
  unmounted(el: HTMLElement & { clickOutsideEvent?: (event: Event) => void }) {
    if (el.clickOutsideEvent) {
      document.body.removeEventListener('click', el.clickOutsideEvent)
    }
  },
}
</script>

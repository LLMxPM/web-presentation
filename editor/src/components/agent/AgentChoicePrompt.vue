<!-- 文件功能：承载智能体结构化单选提问 HITL 交互，支持多题顺序回答、前后切换和自定义回答。 -->
<template>
  <AgentHitlShell
    :title="currentQuestionTitle"
    :subtitle="questionProgressLabel"
    badge="需要回答"
    :loading="loading"
    :can-submit="allAnswered"
    submit-label="提交回答"
    ignore-label="取消本次运行"
    @ignore="emit('ignore')"
    @submit="submitAnswers"
  >
    <div v-if="currentQuestion" class="space-y-2">
      <div class="space-y-1">
        <button
          v-for="option in currentQuestion.options"
          :key="option.label"
          type="button"
          class="flex w-full items-start gap-2 rounded-md border px-2.5 py-2 text-left transition"
          :class="currentAnswer.selectedLabel === option.label
            ? 'border-sky-300 bg-sky-50 text-sky-900'
            : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50'"
          @click="selectOption(option.label)"
        >
          <span class="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border text-[10px]"
            :class="currentAnswer.selectedLabel === option.label ? 'border-sky-500 bg-sky-500 text-white' : 'border-slate-300 text-transparent'">
            ●
          </span>
          <span class="min-w-0">
            <span class="block text-xs font-semibold leading-5">{{ option.label }}</span>
            <span v-if="option.description" class="block text-[11px] leading-5 text-slate-500">{{ option.description }}</span>
          </span>
        </button>
      </div>

      <input
        :value="currentAnswer.customText"
        type="text"
        class="w-full rounded-md border border-slate-200 bg-white px-2.5 py-2 text-xs text-slate-700 outline-none transition placeholder:text-slate-400 focus:border-sky-300"
        placeholder="或直接输入自定义回答"
        @input="handleCustomInput"
      >

      <p v-if="showCurrentAnswerWarning" class="text-[11px] leading-5 text-amber-600">
        请先选择一个选项，或填写自定义回答。
      </p>
    </div>
    <p v-else class="rounded-md border border-amber-200 bg-amber-50 px-2.5 py-2 text-xs leading-5 text-amber-800">
      当前提问缺少可展示的问题，请忽略后重新发起。
    </p>

    <template #footer-left>
      <BaseButton
        v-if="forceReleaseAvailable"
        variant="ghost"
        size="sm"
        :disabled="loading"
        custom-class="rounded-md px-2 py-1 text-xs text-red-600 shadow-none hover:bg-red-50"
        @click="emit('forceRelease')"
      >
        强制释放
      </BaseButton>
      <BaseButton
        variant="ghost"
        size="sm"
        :disabled="currentIndex <= 0 || loading"
        custom-class="rounded-md px-2 py-1 text-xs shadow-none"
        @click="goPrevious"
      >
        上一题
      </BaseButton>
      <BaseButton
        variant="ghost"
        size="sm"
        :disabled="!canGoNext || loading"
        custom-class="rounded-md px-2 py-1 text-xs shadow-none"
        @click="goNext"
      >
        下一题
      </BaseButton>
    </template>
  </AgentHitlShell>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import AgentHitlShell from '@/components/agent/AgentHitlShell.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import type { AgentFeedbackSelection, AgentPendingRequirement, AgentUserFeedbackQuestion } from '@/types/api'

interface AnswerState {
  selectedLabel: string | null
  customText: string
}

const props = withDefaults(defineProps<{
  requirement: AgentPendingRequirement
  loading?: boolean
  forceReleaseAvailable?: boolean
}>(), {
  loading: false,
  forceReleaseAvailable: false,
})

const emit = defineEmits<{
  submit: [selections: AgentFeedbackSelection[]]
  ignore: []
  forceRelease: []
}>()

const currentIndex = ref(0)
const answers = ref<AnswerState[]>([])
const attemptedSubmit = ref(false)

const questions = computed(() => normalizeQuestions(props.requirement.user_feedback_schema))
const currentQuestion = computed(() => questions.value[currentIndex.value] ?? null)
const currentAnswer = computed(() => answers.value[currentIndex.value] ?? { selectedLabel: null, customText: '' })
const currentQuestionTitle = computed(() => currentQuestion.value?.question || '需要补充信息')
const memberSourceLabel = computed(() => props.requirement.member_agent_name ? `来自 ${props.requirement.member_agent_name}` : '')
const questionProgressLabel = computed(() => (
  [memberSourceLabel.value, questions.value.length > 1 ? `${currentIndex.value + 1} / ${questions.value.length}` : '请选择一个答案']
    .filter(Boolean)
    .join(' · ')
))
const currentAnswered = computed(() => isAnswered(currentAnswer.value))
const allAnswered = computed(() => questions.value.length > 0 && questions.value.every((_, index) => isAnswered(answers.value[index])))
const canGoNext = computed(() => currentIndex.value < questions.value.length - 1 && currentAnswered.value)
const showCurrentAnswerWarning = computed(() => attemptedSubmit.value && !currentAnswered.value)

watch(
  questions,
  value => {
    answers.value = value.map(question => buildInitialAnswer(question))
    currentIndex.value = 0
    attemptedSubmit.value = false
  },
  { immediate: true },
)

/**
 * 选择预设选项，并清空同题的自定义回答，保证单题答案互斥。
 */
function selectOption(label: string) {
  answers.value[currentIndex.value] = {
    selectedLabel: label,
    customText: '',
  }
}

/**
 * 写入自定义回答；有内容时清空预设选项，避免同题产生两个答案。
 */
function handleCustomInput(event: Event) {
  const value = (event.target as HTMLInputElement).value
  answers.value[currentIndex.value] = {
    selectedLabel: value.trim() ? null : currentAnswer.value.selectedLabel,
    customText: value,
  }
}

/**
 * 切换到上一题，允许用户回看和修改已回答问题。
 */
function goPrevious() {
  if (currentIndex.value <= 0) {
    return
  }
  currentIndex.value -= 1
}

/**
 * 当前题已回答后才允许进入下一题，保持用户按顺序完成多题。
 */
function goNext() {
  if (!canGoNext.value) {
    attemptedSubmit.value = true
    return
  }
  currentIndex.value += 1
  attemptedSubmit.value = false
}

/**
 * 全部问题完成后一次性提交给后端，恢复 paused run。
 */
function submitAnswers() {
  attemptedSubmit.value = true
  if (!allAnswered.value) {
    const firstMissingIndex = questions.value.findIndex((_, index) => !isAnswered(answers.value[index]))
    if (firstMissingIndex >= 0) {
      currentIndex.value = firstMissingIndex
    }
    return
  }
  emit('submit', questions.value.map((question, index) => {
    const answer = answers.value[index]
    const customText = answer.customText.trim()
    return {
      question: question.question,
      selected_label: customText ? null : answer.selectedLabel,
      custom_text: customText || null,
    }
  }))
}

/**
 * 清理后端问题结构，强制前端按单选处理。
 */
function normalizeQuestions(rawQuestions: AgentUserFeedbackQuestion[]): AgentUserFeedbackQuestion[] {
  return (rawQuestions || []).map(question => ({
    ...question,
    multi_select: false,
    options: Array.isArray(question.options) ? question.options : [],
  })).filter(question => question.question)
}

/**
 * 从 Agno 已选择值恢复初始答案，支持刷新后回到 paused 状态。
 */
function buildInitialAnswer(question: AgentUserFeedbackQuestion): AnswerState {
  const selected = question.selected_options?.[0] ?? ''
  const matchedOption = question.options.find(option => option.label === selected)
  if (matchedOption) {
    return { selectedLabel: matchedOption.label, customText: '' }
  }
  if (selected.startsWith('用户补充：')) {
    return { selectedLabel: null, customText: selected.slice('用户补充：'.length) }
  }
  return { selectedLabel: null, customText: '' }
}

/**
 * 判断单题是否已有有效答案。
 */
function isAnswered(answer: AnswerState | undefined) {
  return Boolean(answer?.selectedLabel || answer?.customText.trim())
}
</script>

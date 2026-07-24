<!-- 文件功能：提供表单标签、说明、必填标记与错误信息之间的语义关联。 -->
<template>
  <div class="flex w-full flex-col gap-1.5">
    <label v-if="label" :for="inputId" class="text-sm font-medium text-[rgb(var(--ui-text))]">
      {{ label }}
      <span v-if="required" class="text-[rgb(var(--ui-danger))]" aria-hidden="true">*</span>
    </label>
    <slot :input-id="inputId" :described-by="describedBy" :invalid="Boolean(error)" />
    <p v-if="description" :id="descriptionId" class="text-xs text-[rgb(var(--ui-text-muted))]">{{ description }}</p>
    <p v-if="error" :id="errorId" class="text-xs text-[rgb(var(--ui-danger))]" role="alert">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, useId } from 'vue'

const props = withDefaults(defineProps<{
  /** 与控件关联的稳定 id；不传时自动生成。 */
  inputId?: string
  /** 标签文本。 */
  label?: string
  /** 控件辅助说明。 */
  description?: string
  /** 当前校验错误；存在时会写入 aria-describedby。 */
  error?: string
  /** 是否在标签上展示必填标记。 */
  required?: boolean
}>(), {
  required: false,
})

const generatedId = useId()
const inputId = computed(() => props.inputId ?? `ui-field-${generatedId}`)
const descriptionId = computed(() => `${inputId.value}-description`)
const errorId = computed(() => `${inputId.value}-error`)
const describedBy = computed(() => [
  props.description ? descriptionId.value : '',
  props.error ? errorId.value : '',
].filter(Boolean).join(' ') || undefined)
</script>

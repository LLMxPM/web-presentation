<!-- 文件功能：基础输入框组件，支持单行、密码及文本域模式，并提供统一的 Label 与错误提示样式。 -->
<template>
  <div class="flex flex-col gap-1.5 w-full">
    <label v-if="label" class="text-sm font-semibold text-slate-700 ml-1">
      {{ label }}
      <span v-if="required" class="text-red-500">*</span>
    </label>
    
    <div class="relative group">
      <!-- Textarea -->
      <textarea
        v-if="type === 'textarea'"
        :value="modelValue"
        @input="handleInput"
        :placeholder="placeholder"
        :rows="rows || 3"
        :disabled="disabled"
        class="input min-h-[80px] py-3 resize-y"
        :class="{ 'border-red-500 focus:border-red-500': error }"
        v-bind="$attrs"
      ></textarea>
      
      <!-- Password with Eye Toggle -->
      <template v-else-if="type === 'password'">
        <input
          :type="showPassword ? 'text' : 'password'"
          :value="modelValue"
          @input="handleInput"
          :placeholder="placeholder"
          :disabled="disabled"
          class="input pr-11"
          :class="{ 'border-red-500 focus:border-red-500': error }"
          v-bind="$attrs"
        />
        <button 
          type="button" 
          @click="showPassword = !showPassword"
          class="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 transition-colors"
        >
          <component :is="showPassword ? EyeOff : Eye" class="w-4 h-4" />
        </button>
      </template>
      
      <!-- Standard Input -->
      <input
        v-else
        :type="type"
        :value="modelValue"
        @input="handleInput"
        :placeholder="placeholder"
        :disabled="disabled"
        class="input"
        :class="{ 'border-red-500 focus:border-red-500': error }"
        v-bind="$attrs"
      />
    </div>
    
    <p v-if="error" class="text-xs text-red-500 ml-1 mt-0.5">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Eye, EyeOff } from 'lucide-vue-next'

defineOptions({
  inheritAttrs: false,
})

/**
 * 基础输入框组件
 */
const props = defineProps<{
  modelValue: string | number
  label?: string
  placeholder?: string
  type?: string
  rows?: number
  disabled?: boolean
  required?: boolean
  error?: string
}>()

const emit = defineEmits(['update:modelValue'])

const showPassword = ref(false)

function handleInput(e: Event) {
  const target = e.target as HTMLInputElement | HTMLTextAreaElement
  emit('update:modelValue', target.value)
}
</script>

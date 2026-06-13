<!-- 文件功能：承载页面版本快照创建弹窗，负责编辑快照名称并提交创建事件。 -->
<template>
  <BaseDialog :model-value="props.modelValue" :title="`创建快照 · ${props.versionLabel}`" size="compact"
    @update:model-value="emit('update:modelValue', $event)">
    <div class="space-y-4">
      <p class="text-sm text-slate-500">
        为这个版本填写一个更容易识别的名称，后续在版本历史里会更好找。名称可留空。
      </p>
      <BaseInput
        :model-value="props.snapshotName"
        label="快照名称"
        placeholder="例如：提审前定稿"
        @update:model-value="emit('update:snapshotName', String($event))"
      />
    </div>

    <template #footer>
      <BaseButton variant="secondary" @click="emit('update:modelValue', false)">
        取消
      </BaseButton>
      <BaseButton variant="primary" :loading="props.loading" @click="emit('submit')">
        创建快照
      </BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import BaseInput from '@/components/ui/BaseInput.vue'

interface Props {
  modelValue: boolean
  versionLabel: string
  snapshotName: string
  loading: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'update:snapshotName': [value: string]
  submit: []
}>()
</script>


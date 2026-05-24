<!-- 文件功能：项目构建弹窗的资源问题区域，展示构建资源错误并提供补充资源入口。 -->
<template>
  <section
    class="rounded-lg border border-amber-200 bg-amber-50/70 p-4"
    data-testid="project-build-resource-issue"
  >
    <div class="flex items-start gap-3">
      <AlertTriangle class="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
      <div class="min-w-0 flex-1">
        <p class="text-sm font-semibold text-amber-900">{{ title }}</p>
        <p class="mt-1 text-xs leading-5 text-amber-700">{{ description }}</p>

        <div v-if="dynamicModulePaths.length" class="mt-3 rounded-lg border border-amber-200 bg-white/70 px-3 py-2">
          <p class="text-xs font-semibold text-amber-900">动态模块</p>
          <div class="mt-2 flex flex-wrap gap-2">
            <span
              v-for="modulePath in dynamicModulePaths"
              :key="modulePath"
              class="rounded-md bg-amber-100 px-2 py-1 font-mono text-xs text-amber-800"
            >
              {{ modulePath }}
            </span>
          </div>
        </div>

        <div v-if="missingAssetNames.length" class="mt-3 rounded-lg border border-rose-200 bg-white/70 px-3 py-2">
          <p class="text-xs font-semibold text-rose-800">缺失资源</p>
          <div class="mt-2 flex flex-wrap gap-2">
            <span
              v-for="assetName in missingAssetNames"
              :key="assetName"
              class="rounded-md bg-rose-100 px-2 py-1 font-mono text-xs text-rose-700"
            >
              {{ assetName }}
            </span>
          </div>
        </div>

        <div v-if="candidateAssetNames.length" class="mt-3 flex flex-wrap gap-2">
          <button
            v-for="assetName in candidateAssetNames"
            :key="assetName"
            type="button"
            class="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-semibold transition"
            :class="isSelected(assetName) ? 'border-amber-300 bg-white text-amber-900' : 'border-amber-200 bg-amber-100 text-amber-800 hover:border-amber-300'"
            @click="emit('addAsset', assetName)"
          >
            <Check v-if="isSelected(assetName)" class="h-3.5 w-3.5" />
            <Plus v-else class="h-3.5 w-3.5" />
            加入 {{ assetName }}
          </button>
        </div>

        <div class="mt-3 flex flex-wrap gap-2">
          <BaseButton
            v-if="canSaveExtraAssets"
            variant="secondary"
            size="sm"
            :loading="extraAssetsSaving"
            custom-class="whitespace-nowrap"
            @click="emit('saveExtraAssets')"
          >
            保存额外资源
          </BaseButton>
          <BaseButton variant="primary" size="sm" :loading="loading" custom-class="whitespace-nowrap" @click="emit('submit')">
            重新构建
          </BaseButton>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { AlertTriangle, Check, Plus } from '@lucide/vue'

import BaseButton from '@/components/ui/BaseButton.vue'

const props = defineProps<{
  title: string
  description: string
  dynamicModulePaths: string[]
  missingAssetNames: string[]
  candidateAssetNames: string[]
  selectedAssetNames: string[]
  canSaveExtraAssets: boolean
  extraAssetsSaving?: boolean
  loading?: boolean
}>()

const emit = defineEmits<{
  addAsset: [assetName: string]
  saveExtraAssets: []
  submit: []
}>()

/**
 * 判断候选资源是否已经在额外资源草稿中。
 * @param assetName 资源名
 */
function isSelected(assetName: string): boolean {
  return props.selectedAssetNames.includes(assetName)
}
</script>

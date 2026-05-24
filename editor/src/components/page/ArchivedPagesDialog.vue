<!-- 文件功能：展示当前项目下的归档页面列表，支持搜索、查看截图并恢复页面。 -->
<template>
  <BaseDialog :model-value="modelValue" title="归档页面" width="860px" @update:modelValue="handleDialogVisibleChange">
    <div class="flex flex-col gap-4">
      <BaseInput v-model="keyword" placeholder="按页面名称、编码或源码搜索" type="text" />

      <div class="overflow-hidden rounded-2xl border border-slate-200 bg-slate-50/50">
        <div
          class="flex items-center justify-between border-b border-slate-200 px-4 py-3 text-xs font-semibold text-slate-500">
          <span>共 {{ archivedPages.length }} 个归档页面</span>
          <span>可搜索并恢复页面</span>
        </div>

        <div v-if="query.isFetching.value" class="flex items-center justify-center py-12 text-sm text-slate-500">
          正在加载归档页面...
        </div>

        <div v-else-if="archivedPages.length === 0"
          class="flex flex-col items-center justify-center gap-2 py-12 text-slate-500">
          <p class="text-sm font-semibold">{{ keyword.trim() ? '没有匹配的归档页面。' : '当前没有归档页面。' }}</p>
          <p class="text-xs text-slate-400">恢复后的页面会重新出现在页面列表。</p>
        </div>

        <div v-else class="divide-y divide-slate-200">
          <div v-for="page in archivedPages" :key="page.id"
            class="flex items-center justify-between gap-4 bg-white px-4 py-4">
            <div class="w-40 shrink-0 overflow-hidden rounded-xl border border-slate-200 bg-slate-100"
              :style="{ aspectRatio: screenshotAspectRatio }">
              <img v-if="page.screenshot_url" :src="page.screenshot_url" :alt="`${page.title} 最新截图`"
                class="h-full w-full object-cover" loading="lazy">
              <div v-else class="flex h-full w-full flex-col items-center justify-center gap-1.5 text-slate-400">
                <ImageOff class="h-5 w-5" />
                <span class="text-[10px] font-semibold">暂无截图</span>
              </div>
            </div>

            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-3">
                <h4 class="truncate text-sm font-semibold text-slate-900">{{ page.title }}</h4>
                <span class="font-mono text-[10px] font-bold uppercase tracking-widest text-slate-400">{{ page.code
                  }}</span>
              </div>
            </div>

            <BaseButton variant="secondary" :loading="restoringPageId === page.id" @click="handleRestorePage(page.id)">
              恢复
            </BaseButton>
          </div>
        </div>
      </div>
    </div>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { ImageOff } from '@lucide/vue'

import { listPages, updatePage } from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import type { PageItem } from '@/types/api'
import { Message } from '@/utils/message'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import BaseInput from '@/components/ui/BaseInput.vue'

const props = withDefaults(defineProps<{
  modelValue: boolean
  projectId: number
  screenshotAspectRatio?: string
}>(), {
  screenshotAspectRatio: '16 / 9',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  restored: []
}>()

const queryClient = useQueryClient()
const keyword = ref('')
const restoringPageId = ref<number | null>(null)

const query = useQuery(
  computed(() => ({
    queryKey: ['pages-by-project', props.projectId, 'archived', keyword.value.trim()],
    queryFn: () =>
      listPages({
        page: 1,
        page_size: 100,
        project_id: props.projectId,
        status: 'archived',
        keyword: keyword.value.trim(),
        sort_by: 'updated_at',
        sort_order: 'desc',
      }),
    enabled: props.modelValue && props.projectId > 0,
  })),
)

const archivedPages = computed<PageItem[]>(() => query.data.value?.items ?? [])

const restoreMutation = useMutation({
  mutationFn: (pageId: number) => updatePage(pageId, { status: 'active' }),
})

watch(
  () => props.modelValue,
  (visible) => {
    if (!visible) {
      keyword.value = ''
      restoringPageId.value = null
    }
  },
)

/**
 * 关闭弹窗并同步给父组件。
 * @param value 最新显示状态
 */
function handleDialogVisibleChange(value: boolean): void {
  emit('update:modelValue', value)
}

/**
 * 将归档页面恢复为启用状态，并刷新启用列表与归档列表缓存。
 * @param pageId 页面 ID
 */
async function handleRestorePage(pageId: number): Promise<void> {
  restoringPageId.value = pageId
  try {
    await restoreMutation.mutateAsync(pageId)
    await queryClient.invalidateQueries({ queryKey: ['pages-by-project', props.projectId] })
    emit('restored')
    Message.success('页面已恢复。')
  } catch (error) {
    Message.error(getErrorMessage(error, '恢复页面失败。'))
  } finally {
    restoringPageId.value = null
  }
}
</script>

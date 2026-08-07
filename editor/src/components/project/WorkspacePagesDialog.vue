<!-- 文件功能：展示当前工作空间内项目页面的分页搜索弹窗，并承载页面级快捷操作。 -->
<template>
  <UiDialog :open="modelValue" title="所有页面" size="wide" @update:open="handleDialogVisibleChange">
    <div class="flex min-h-0 flex-col gap-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <SimpleSearchBar
          v-model="keyword"
          class="w-full min-w-64 max-w-md"
          placeholder="按页面名称、编码或源码搜索"
          aria-label="搜索所有页面"
        />
        <span class="shrink-0 text-xs font-semibold text-text-muted">共 {{ total }} 个页面</span>
      </div>

      <div class="min-h-0 overflow-y-auto rounded-2xl border border-border bg-canvas/50 p-4">
        <div v-if="query.isPending.value" class="flex items-center justify-center py-16 text-sm text-text-muted">
          正在加载页面...
        </div>

        <div v-else-if="query.isError.value" class="flex flex-col items-center justify-center gap-3 py-16 text-center">
          <p class="text-sm font-semibold text-text-emphasis">页面列表暂不可用</p>
          <p class="text-xs text-text-muted">无法读取当前工作空间的页面，请重试。</p>
          <UiButton variant="secondary" size="sm" @click="query.refetch()">重试</UiButton>
        </div>

        <div v-else-if="pages.length === 0" class="flex flex-col items-center justify-center gap-2 py-16 text-center text-text-muted">
          <p class="text-sm font-semibold">{{ searchKeyword ? '没有匹配的页面。' : '当前工作空间暂无项目页面。' }}</p>
          <p class="text-xs text-text-disabled">可调整搜索条件，或先在项目中创建页面。</p>
        </div>

        <div v-else class="grid grid-cols-[repeat(auto-fill,minmax(min(100%,18rem),1fr))] gap-4">
          <WorkspacePageCard
            v-for="pageItem in pages"
            :key="pageItem.id"
            :page="pageItem"
            :screenshot-pending="screenshotPendingPageId === pageItem.id"
            :screenshot-disabled="screenshotPendingPageId !== null"
            :archive-pending="archivingPageId === pageItem.id"
            @open="handleOpenPage"
            @copy="openPageCopyDialog"
            @copy-name="handleCopyPageName"
            @copy-code="handleCopyPageCode"
            @screenshot="handleSavePageScreenshot"
            @download="handleDownloadScreenshot"
            @archive="handleArchivePage"
          />
        </div>
      </div>

      <PaginationControl
        v-if="total > 0"
        :page="page"
        :page-size="pageSize"
        :total="total"
        @update:page="page = $event"
        @update:page-size="handlePageSizeChange"
      />
    </div>

  </UiDialog>

  <PageCopyToProjectDialog
    v-model="pageCopyDialogVisible"
    :page="copyingPage"
    :workspace-id="workspaceId"
    :current-project-id="copyingPage?.project_id ?? 0"
    :loading="pageCopySaving"
    @submit="handlePageCopySubmit"
  />
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { useRouter } from 'vue-router'

import {
  copyPageToProject,
  listPages,
  savePageScreenshot,
  updatePage,
} from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import PageCopyToProjectDialog from '@/components/page/PageCopyToProjectDialog.vue'
import PaginationControl from '@/components/ui/PaginationControl.vue'
import SimpleSearchBar from '@/components/patterns/SimpleSearchBar.vue'
import WorkspacePageCard from '@/components/project/WorkspacePageCard.vue'
import { UiButton, UiDialog } from '@/components/ui'
import type { PageCopyToProjectPayload, PageItem } from '@/types/api'
import { createConfirm, Message } from '@/utils/message'
import { downloadPageScreenshot } from '@/utils/page-screenshot-download'
import { buildPageDetailPath } from '@/utils/workspace-routes'

const props = defineProps<{
  modelValue: boolean
  workspaceId: number
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const queryClient = useQueryClient()
const router = useRouter()
const keyword = ref('')
const searchKeyword = ref('')
const page = ref(1)
const pageSize = ref(24)
const screenshotPendingPageId = ref<number | null>(null)
const archivingPageId = ref<number | null>(null)
const pageCopyDialogVisible = ref(false)
const pageCopySaving = ref(false)
const copyingPage = ref<PageItem | null>(null)
let searchDebounceTimer: number | null = null

const query = useQuery(
  computed(() => ({
    queryKey: [
      'pages-by-workspace',
      props.workspaceId,
      'active-assigned',
      searchKeyword.value,
      page.value,
      pageSize.value,
    ],
    queryFn: () => listPages({
      page: page.value,
      page_size: pageSize.value,
      workspace_id: props.workspaceId,
      project_assigned: true,
      status: 'active',
      keyword: searchKeyword.value || undefined,
      sort_by: 'updated_at',
      sort_order: 'desc',
    }),
    enabled: props.modelValue && props.workspaceId > 0,
  })),
)

const pages = computed<PageItem[]>(() => query.data.value?.items ?? [])
const total = computed(() => query.data.value?.total ?? 0)

const archiveMutation = useMutation({
  mutationFn: (pageId: number) => updatePage(pageId, { status: 'archived' }),
})

watch(keyword, () => {
  if (searchDebounceTimer !== null) {
    window.clearTimeout(searchDebounceTimer)
  }
  searchDebounceTimer = window.setTimeout(() => {
    searchKeyword.value = keyword.value.trim()
    page.value = 1
    searchDebounceTimer = null
  }, 300)
})

watch(
  () => [props.modelValue, props.workspaceId] as const,
  ([visible]) => {
    if (visible) {
      return
    }
    resetDialogState()
  },
)

watch(
  () => props.workspaceId,
  () => {
    if (props.modelValue) {
      resetDialogState()
    }
  },
)

watch(
  () => query.data.value,
  (data) => {
    if (data && data.items.length === 0 && page.value > 1) {
      page.value -= 1
    }
  },
)

onBeforeUnmount(() => {
  if (searchDebounceTimer !== null) {
    window.clearTimeout(searchDebounceTimer)
  }
})

/**
 * 关闭弹窗并同步父组件状态。
 * @param value 最新显示状态
 */
function handleDialogVisibleChange(value: boolean): void {
  emit('update:modelValue', value)
}

/**
 * 清理弹窗搜索、分页和操作状态，确保下一次打开从第一页开始。
 */
function resetDialogState(): void {
  keyword.value = ''
  searchKeyword.value = ''
  page.value = 1
  pageSize.value = 24
  screenshotPendingPageId.value = null
  archivingPageId.value = null
  pageCopyDialogVisible.value = false
  pageCopySaving.value = false
  copyingPage.value = null
}

/**
 * 切换每页数量并回到第一页。
 * @param size 新的页面数量
 */
function handlePageSizeChange(size: number): void {
  pageSize.value = size
  page.value = 1
}

/**
 * 跳转到页面详情，页面范围已由接口保证归属于项目。
 * @param pageItem 待查看页面
 */
function handleOpenPage(pageItem: PageItem): void {
  if (!pageItem.project_id) {
    Message.error('该页面暂未归属项目，无法打开详情。')
    return
  }
  emit('update:modelValue', false)
  void router.push(buildPageDetailPath(props.workspaceId, pageItem.project_id, pageItem.id))
}

/**
 * 打开页面复制到其它项目的配置弹窗。
 * @param pageItem 待复制页面
 */
function openPageCopyDialog(pageItem: PageItem): void {
  copyingPage.value = pageItem
  pageCopyDialogVisible.value = true
}

/**
 * 复制页面名称到剪贴板。
 * @param pageItem 待复制名称的页面
 */
async function handleCopyPageName(pageItem: PageItem): Promise<void> {
  try {
    await navigator.clipboard.writeText(pageItem.title)
    Message.success('页面名称已复制。')
  } catch {
    Message.error('复制失败，请检查浏览器剪贴板权限。')
  }
}

/**
 * 复制页面编码到剪贴板，保持页面卡片与项目卡片的身份复制行为一致。
 * @param pageItem 待复制编码的页面
 */
async function handleCopyPageCode(pageItem: PageItem): Promise<void> {
  try {
    await navigator.clipboard.writeText(pageItem.code)
    Message.success('页面编码已复制。')
  } catch {
    Message.error('复制失败，请检查浏览器剪贴板权限。')
  }
}

/**
 * 调用截图任务生成页面最新截图，并刷新当前页面查询。
 * @param pageItem 待截图页面
 */
async function handleSavePageScreenshot(pageItem: PageItem): Promise<void> {
  if (screenshotPendingPageId.value !== null) {
    return
  }
  screenshotPendingPageId.value = pageItem.id
  try {
    await savePageScreenshot(pageItem.id)
    await queryClient.invalidateQueries({ queryKey: ['pages-by-workspace', props.workspaceId] })
    Message.success(`「${pageItem.title}」截图已更新。`)
  } catch (error) {
    Message.error(getErrorMessage(error, '更新页面截图失败。'))
  } finally {
    screenshotPendingPageId.value = null
  }
}

/**
 * 下载页面截图；截图缺失或已过期时先生成最新截图，再使用最新结果下载。
 * @param pageItem 待下载截图的页面
 */
async function handleDownloadScreenshot(pageItem: PageItem): Promise<void> {
  if (screenshotPendingPageId.value !== null) {
    return
  }

  screenshotPendingPageId.value = pageItem.id
  try {
    let downloadablePage = pageItem
    if (!pageItem.screenshot_url || !pageItem.screenshot_is_latest) {
      downloadablePage = await savePageScreenshot(pageItem.id)
      await queryClient.invalidateQueries({ queryKey: ['pages-by-workspace', props.workspaceId] })
    }

    if (!downloadablePage.screenshot_url || !downloadablePage.screenshot_is_latest) {
      throw new Error('截图生成完成，但未返回可下载的最新截图。')
    }

    downloadPageScreenshot(
      downloadablePage.screenshot_url,
      downloadablePage.title,
      downloadablePage.screenshot_version_no,
    )
  } catch (error) {
    Message.error(getErrorMessage(error, '下载页面截图失败。'))
  } finally {
    screenshotPendingPageId.value = null
  }
}

/**
 * 归档页面并刷新页面列表、项目列表及项目页面统计。
 * @param pageItem 待归档页面
 */
async function handleArchivePage(pageItem: PageItem): Promise<void> {
  const confirmed = await createConfirm(`归档后「${pageItem.title}」将从所有页面列表中移除，确定归档吗？`, '归档页面')
  if (!confirmed) {
    return
  }

  archivingPageId.value = pageItem.id
  try {
    await archiveMutation.mutateAsync(pageItem.id)
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['pages-by-workspace', props.workspaceId] }),
      queryClient.invalidateQueries({ queryKey: ['projects-by-ws', props.workspaceId] }),
      pageItem.project_id
        ? queryClient.invalidateQueries({ queryKey: ['pages-by-project', pageItem.project_id] })
        : Promise.resolve(),
    ])
    Message.success('页面已归档。')
  } catch (error) {
    Message.error(getErrorMessage(error, '归档页面失败。'))
  } finally {
    archivingPageId.value = null
  }
}

/**
 * 将页面复制到目标项目并刷新当前工作空间的页面与项目统计。
 * @param payload 页面复制配置
 */
async function handlePageCopySubmit(payload: PageCopyToProjectPayload): Promise<void> {
  if (!copyingPage.value) {
    return
  }

  pageCopySaving.value = true
  try {
    const copiedPage = await copyPageToProject(copyingPage.value.id, payload)
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['pages-by-workspace', props.workspaceId] }),
      queryClient.invalidateQueries({ queryKey: ['projects-by-ws', props.workspaceId] }),
      copiedPage.project_id
        ? queryClient.invalidateQueries({ queryKey: ['pages-by-project', copiedPage.project_id] })
        : Promise.resolve(),
    ])
    pageCopyDialogVisible.value = false
    copyingPage.value = null
    Message.success('页面已复制到目标项目。')
  } catch (error) {
    Message.error(getErrorMessage(error, '复制页面失败。'))
  } finally {
    pageCopySaving.value = false
  }
}
</script>

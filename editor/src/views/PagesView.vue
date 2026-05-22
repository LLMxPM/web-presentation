<!-- 文件功能：展示指定项目内的页面资源列表，并集中承载页面编辑、归档、路由分组与项目级配置入口。 -->
<template>
  <div data-testid="project-pages-view" class="pages-view flex h-full min-h-0 flex-col">
    <header class="mb-4 shrink-0 animate-in fade-in slide-in-from-top-4 duration-700">
      <PageTitleBar
        v-if="projectDetails"
        :title="projectDetails.name"
        :code="projectDetails.code"
        :description="projectDetails.description"
      >
        <template #title-leading>
          <button
            type="button"
            class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-500 transition-all hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-600 disabled:cursor-not-allowed disabled:opacity-50"
            title="返回空间首页"
            aria-label="返回空间首页"
            :disabled="!workspaceId"
            @click="goToWorkspaceHome"
          >
            <ArrowLeft class="h-4 w-4" />
          </button>
        </template>

        <template #title-actions>
          <button type="button" class="project-identity-action" title="修改项目基础信息" aria-label="修改项目基础信息"
            @click="openProjectIdentityDialog">
            <SquarePen class="h-3.5 w-3.5" />
          </button>
        </template>

        <template #actions>
          <BaseButton variant="primary" :loading="previewLoading" :disabled="!projectDetails"
            @click="handlePreviewProject">
            <template #icon>
              <Play class="h-4 w-4" />
            </template>
            预览
          </BaseButton>
          <BaseButton variant="ghost" :disabled="!projectDetails" @click="openPresentationConfigDialog">
            <template #icon>
              <SlidersHorizontal class="h-4 w-4" />
            </template>
            样式
          </BaseButton>
          <div class="page-card-size-control" role="group" aria-label="预览卡片大小">
            <button
              v-for="option in pageCardSizeOptions"
              :key="option.value"
              type="button"
              class="page-card-size-button"
              :class="pageCardSize === option.value ? 'page-card-size-button-active' : ''"
              :title="`卡片${option.label}`"
              :aria-label="`卡片${option.label}`"
              :aria-pressed="pageCardSize === option.value"
              @click="setPageCardSize(option.value)"
            >
              <component :is="option.icon" class="h-3.5 w-3.5" />
            </button>
          </div>
          <BaseButton variant="primary" :disabled="!projectDetails" @click="openCreateDialog">
            <template #icon>
              <Plus class="h-4 w-4" />
            </template>
            新增页面
          </BaseButton>
        </template>
      </PageTitleBar>
    </header>

    <div v-if="query.isFetching.value" class="flex min-h-0 flex-1 flex-col items-center justify-center gap-4">
      <div class="h-12 w-12 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent"></div>
      <span class="animate-pulse font-bold text-slate-400">资源库同步中...</span>
    </div>

    <div v-else class="min-h-0 flex-1 space-y-10 overflow-y-auto pb-12 pr-1">
      <section class="space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-4">
          <div class="flex flex-wrap items-center gap-3">
            <h2 class="text-lg font-bold text-slate-900">已加入路由</h2>
            <span class="text-xs font-semibold text-slate-400">{{ routedPageEntries.length }} 条路由绑定</span>
          </div>
          <div class="flex flex-wrap items-center justify-end gap-2">
            <BaseButton
              data-testid="batch-refresh-routed-page-screenshots"
              variant="ghost"
              size="sm"
              :loading="batchScreenshotRefreshScope === 'routed'"
              :disabled="!projectDetails || routedRefreshableScreenshotCount === 0 || screenshotPendingPageId !== null || batchScreenshotRefreshing"
              @click="handleRefreshSectionPageScreenshots('routed')"
            >
              <template #icon>
                <RefreshCw class="h-3.5 w-3.5" />
              </template>
              刷新截图
              <span v-if="routedRefreshableScreenshotCount > 0">({{ routedRefreshableScreenshotCount }})</span>
            </BaseButton>
            <BaseButton variant="ghost" size="sm" :disabled="!projectDetails" @click="openRouteConfigDialog">
              <template #icon>
                <RouteIcon class="h-3.5 w-3.5" />
              </template>
              路由
            </BaseButton>
            <BaseButton
              data-testid="project-build-open"
              variant="primary"
              size="sm"
              custom-class="project-build-action"
              :disabled="!projectDetails"
              @click="openBuildDialog"
            >
              <template #icon>
                <Hammer class="h-3.5 w-3.5" />
              </template>
              构建
            </BaseButton>
            <label
              v-if="routedPagesForBatch.length > 0"
              class="batch-select-toggle"
              :class="isAllRoutedSelected ? 'batch-select-toggle-active' : ''"
            >
              <input
                data-testid="batch-routed-select-all"
                type="checkbox"
                class="sr-only"
                :checked="isAllRoutedSelected"
                @change="handleRoutedSelectAllChange"
              >
              <span class="batch-select-box">
                <Check v-if="isAllRoutedSelected" class="h-3 w-3" />
              </span>
              <span>{{ isAllRoutedSelected ? '已全选' : '全选' }}</span>
            </label>
            <div v-if="selectedRoutedPages.length > 0" class="batch-toolbar">
              <span class="batch-toolbar-count">已选 {{ selectedRoutedPages.length }}</span>
              <button type="button" data-testid="batch-routed-remove-route" class="batch-toolbar-action" :disabled="batchActionPending !== null" @click="handleBatchRemoveFromRoute">
                <RouteOff class="h-3.5 w-3.5" />
                移出路由
              </button>
              <button type="button" data-testid="batch-routed-screenshot" class="batch-toolbar-action" :disabled="batchActionPending !== null" @click="handleBatchSaveScreenshots('routed')">
                <Camera class="h-3.5 w-3.5" />
                截图
              </button>
              <button type="button" data-testid="batch-routed-copy" class="batch-toolbar-action" :disabled="batchActionPending !== null" @click="openBatchCopyDialog('routed')">
                <Copy class="h-3.5 w-3.5" />
                复制
              </button>
              <button type="button" data-testid="batch-routed-archive" class="batch-toolbar-action text-amber-700 hover:bg-amber-50" :disabled="batchActionPending !== null" @click="handleBatchArchivePages('routed')">
                <Archive class="h-3.5 w-3.5" />
                归档
              </button>
              <button type="button" class="batch-toolbar-icon" title="清空选择" aria-label="清空已加入路由选择" @click="clearRoutedSelection">
                <X class="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>

        <div v-if="routedPageEntries.length === 0"
          class="rounded-lg border border-dashed border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-400">
          当前没有页面加入项目路由。
        </div>

        <div v-else class="grid gap-4" :style="pageCardGridStyle">
          <article v-for="entry in routedPageEntries" :key="entry.key" data-testid="page-card"
            class="group/card relative flex cursor-pointer flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm transition-all duration-300 hover:-translate-y-1 hover:border-indigo-300 hover:shadow-md"
            :class="isRoutedPageSelected(entry.page.id) ? 'border-indigo-400 ring-2 ring-indigo-100' : ''"
            @click="goToPage(entry.page.id)">
            <div class="relative overflow-hidden bg-slate-100" :style="{ aspectRatio: projectScreenshotAspectRatio }">
              <img v-if="entry.page.screenshot_url" :src="entry.page.screenshot_url" :alt="`${entry.page.title} 截图`"
                class="h-full w-full object-cover transition-transform duration-300 group-hover/card:scale-[1.02]"
                loading="lazy">
              <div v-else class="flex h-full w-full flex-col items-center justify-center gap-1.5 text-slate-400">
                <Layout class="h-6 w-6" />
                <span class="text-[10px] font-semibold tracking-wide">尚未保存截图</span>
              </div>
              <div
                class="page-card-topbar"
                :class="isRoutedPageSelected(entry.page.id) ? 'page-card-topbar-active' : ''"
              >
                <div class="page-card-route-path">
                  <RouteIcon class="h-3 w-3 shrink-0" />
                  <span class="min-w-0 truncate">{{ entry.routePath }}</span>
                  <span v-if="entry.isDuplicate" class="shrink-0 rounded-full bg-amber-50 px-1.5 py-0.5 text-amber-700">
                    重复 {{ entry.duplicateIndex }}/{{ entry.duplicateTotal }}
                  </span>
                </div>
                <div class="page-card-top-actions">
                  <span v-if="entry.page.screenshot_url && !entry.page.screenshot_is_latest" class="page-card-stale-badge">
                    旧截图
                  </span>
                  <label
                    class="page-card-select"
                    :class="isRoutedPageSelected(entry.page.id) ? 'page-card-select-active' : ''"
                    title="选择页面"
                    aria-label="选择页面"
                    @click.stop
                  >
                    <input
                      :data-testid="`batch-routed-select-${entry.page.id}`"
                      type="checkbox"
                      class="sr-only"
                      :checked="isRoutedPageSelected(entry.page.id)"
                      @change="event => handleRoutedPageSelectionChange(entry.page.id, event)"
                    >
                    <span class="page-card-select-box">
                      <Check v-if="isRoutedPageSelected(entry.page.id)" class="h-3 w-3" />
                    </span>
                  </label>
                </div>
              </div>
              <div
                class="pointer-events-none absolute inset-x-2 bottom-2 z-20 flex translate-y-1 justify-end gap-1 opacity-0 transition-all group-hover/card:pointer-events-auto group-hover/card:translate-y-0 group-hover/card:opacity-100">
                <button type="button" class="page-card-action" title="管理路由" aria-label="管理路由"
                  @click.stop="openRouteConfigDialog">
                  <RouteIcon class="h-3.5 w-3.5" />
                </button>
                <button type="button" class="page-card-action" title="复制到其他项目" aria-label="复制到其他项目"
                  @click.stop="openPageCopyDialog(entry.page)">
                  <Copy class="h-3.5 w-3.5" />
                </button>
                <button type="button" data-testid="page-card-screenshot" class="page-card-action" title="更新截图" aria-label="更新截图"
                  :disabled="screenshotPendingPageId !== null || batchScreenshotRefreshing" @click.stop="handleSavePageScreenshot(entry.page)">
                  <LoaderCircle v-if="screenshotPendingPageId === entry.page.id" class="h-3.5 w-3.5 animate-spin" />
                  <Camera v-else class="h-3.5 w-3.5" />
                </button>
                <button type="button" class="page-card-action text-amber-600 hover:bg-amber-50" title="归档页面"
                  aria-label="归档页面" :disabled="archivingPageId === entry.page.id"
                  @click.stop="handleArchivePage(entry.page)">
                  <Archive class="h-3.5 w-3.5" />
                </button>
              </div>
            </div>

            <div class="p-3">
              <div class="flex min-w-0 items-center gap-2">
                <h3
                  class="truncate text-sm font-bold leading-tight text-slate-800 transition-colors group-hover/card:text-indigo-600"
                  :title="entry.page.title">
                  {{ entry.page.title }}
                </h3>
                <div class="shrink-0 font-mono text-[10px] font-semibold uppercase tracking-widest text-slate-400">
                  {{ entry.page.code }}
                </div>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section class="space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-4">
          <div class="flex flex-wrap items-center gap-3">
            <h2 class="text-lg font-bold text-slate-900">未加入路由</h2>
            <span class="text-xs font-semibold text-slate-400">{{ unroutedPages.length }} 个页面</span>
          </div>
          <div class="flex flex-wrap items-center justify-end gap-2">
            <BaseButton
              data-testid="batch-refresh-unrouted-page-screenshots"
              variant="ghost"
              size="sm"
              :loading="batchScreenshotRefreshScope === 'unrouted'"
              :disabled="!projectDetails || unroutedRefreshableScreenshotCount === 0 || screenshotPendingPageId !== null || batchScreenshotRefreshing"
              @click="handleRefreshSectionPageScreenshots('unrouted')"
            >
              <template #icon>
                <RefreshCw class="h-3.5 w-3.5" />
              </template>
              刷新截图
              <span v-if="unroutedRefreshableScreenshotCount > 0">({{ unroutedRefreshableScreenshotCount }})</span>
            </BaseButton>
            <BaseButton variant="ghost" size="sm" :disabled="!projectDetails" @click="archivedPagesDialogVisible = true">
              <template #icon>
                <Archive class="h-3.5 w-3.5" />
              </template>
              归档页面
            </BaseButton>
            <label
              v-if="unroutedPages.length > 0"
              class="batch-select-toggle"
              :class="isAllUnroutedSelected ? 'batch-select-toggle-active' : ''"
            >
              <input
                data-testid="batch-unrouted-select-all"
                type="checkbox"
                class="sr-only"
                :checked="isAllUnroutedSelected"
                @change="handleUnroutedSelectAllChange"
              >
              <span class="batch-select-box">
                <Check v-if="isAllUnroutedSelected" class="h-3 w-3" />
              </span>
              <span>{{ isAllUnroutedSelected ? '已全选' : '全选' }}</span>
            </label>
            <div v-if="selectedUnroutedPages.length > 0" class="batch-toolbar">
              <span class="batch-toolbar-count">已选 {{ selectedUnroutedPages.length }}</span>
              <button type="button" data-testid="batch-unrouted-add-route" class="batch-toolbar-action" :disabled="batchActionPending !== null" @click="handleBatchAddToRoute">
                <ListPlus class="h-3.5 w-3.5" />
                加入路由
              </button>
              <button type="button" data-testid="batch-unrouted-screenshot" class="batch-toolbar-action" :disabled="batchActionPending !== null" @click="handleBatchSaveScreenshots('unrouted')">
                <Camera class="h-3.5 w-3.5" />
                截图
              </button>
              <button type="button" data-testid="batch-unrouted-copy" class="batch-toolbar-action" :disabled="batchActionPending !== null" @click="openBatchCopyDialog('unrouted')">
                <Copy class="h-3.5 w-3.5" />
                复制
              </button>
              <button type="button" data-testid="batch-unrouted-archive" class="batch-toolbar-action text-amber-700 hover:bg-amber-50" :disabled="batchActionPending !== null" @click="handleBatchArchivePages('unrouted')">
                <Archive class="h-3.5 w-3.5" />
                归档
              </button>
              <button type="button" class="batch-toolbar-icon" title="清空选择" aria-label="清空未加入路由选择" @click="clearUnroutedSelection">
                <X class="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>

        <div class="grid gap-4" :style="pageCardGridStyle">
          <article v-for="page in unroutedPages" :key="page.id" data-testid="page-card"
            class="group/card relative flex cursor-pointer flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm transition-all duration-300 hover:-translate-y-1 hover:border-indigo-300 hover:shadow-md"
            :class="isUnroutedPageSelected(page.id) ? 'border-indigo-400 ring-2 ring-indigo-100' : ''"
            @click="goToPage(page.id)">
            <div class="relative overflow-hidden bg-slate-100" :style="{ aspectRatio: projectScreenshotAspectRatio }">
              <img v-if="page.screenshot_url" :src="page.screenshot_url" :alt="`${page.title} 截图`"
                class="h-full w-full object-cover transition-transform duration-300 group-hover/card:scale-[1.02]"
                loading="lazy">
              <div v-else class="flex h-full w-full flex-col items-center justify-center gap-1.5 text-slate-400">
                <Layout class="h-6 w-6" />
                <span class="text-[10px] font-semibold tracking-wide">尚未保存截图</span>
              </div>
              <div
                class="page-card-topbar page-card-topbar-end"
                :class="isUnroutedPageSelected(page.id) ? 'page-card-topbar-active' : ''"
              >
                <div class="page-card-top-actions">
                  <span v-if="page.screenshot_url && !page.screenshot_is_latest" class="page-card-stale-badge">
                    旧截图
                  </span>
                  <label
                    class="page-card-select"
                    :class="isUnroutedPageSelected(page.id) ? 'page-card-select-active' : ''"
                    title="选择页面"
                    aria-label="选择页面"
                    @click.stop
                  >
                    <input
                      :data-testid="`batch-unrouted-select-${page.id}`"
                      type="checkbox"
                      class="sr-only"
                      :checked="isUnroutedPageSelected(page.id)"
                      @change="event => handleUnroutedPageSelectionChange(page.id, event)"
                    >
                    <span class="page-card-select-box">
                      <Check v-if="isUnroutedPageSelected(page.id)" class="h-3 w-3" />
                    </span>
                  </label>
                </div>
              </div>
              <div
                class="pointer-events-none absolute inset-x-2 bottom-2 z-20 flex translate-y-1 justify-end gap-1 opacity-0 transition-all group-hover/card:pointer-events-auto group-hover/card:translate-y-0 group-hover/card:opacity-100">
                <button type="button" class="page-card-action" title="加入顶层路由" aria-label="加入顶层路由"
                  :disabled="pageRoutePendingId === page.id" @click.stop="handleAddPageToRoute(page)">
                  <RouteIcon class="h-3.5 w-3.5" />
                </button>
                <button type="button" class="page-card-action" title="复制到其他项目" aria-label="复制到其他项目"
                  @click.stop="openPageCopyDialog(page)">
                  <Copy class="h-3.5 w-3.5" />
                </button>
                <button type="button" data-testid="page-card-screenshot" class="page-card-action" title="更新截图" aria-label="更新截图"
                  :disabled="screenshotPendingPageId !== null || batchScreenshotRefreshing" @click.stop="handleSavePageScreenshot(page)">
                  <LoaderCircle v-if="screenshotPendingPageId === page.id" class="h-3.5 w-3.5 animate-spin" />
                  <Camera v-else class="h-3.5 w-3.5" />
                </button>
                <button type="button" class="page-card-action text-amber-600 hover:bg-amber-50" title="归档页面"
                  aria-label="归档页面" :disabled="archivingPageId === page.id" @click.stop="handleArchivePage(page)">
                  <Archive class="h-3.5 w-3.5" />
                </button>
              </div>
            </div>

            <div class="p-3">
              <div class="flex min-w-0 items-center gap-2">
                <h3
                  class="truncate text-sm font-bold leading-tight text-slate-800 transition-colors group-hover/card:text-indigo-600"
                  :title="page.title">
                  {{ page.title }}
                </h3>
                <div class="shrink-0 font-mono text-[10px] font-semibold uppercase tracking-widest text-slate-400">
                  {{ page.code }}
                </div>
              </div>
            </div>
          </article>

          <button type="button"
            class="flex min-h-[220px] flex-col items-center justify-center rounded-lg border-2 border-dashed border-slate-200 bg-slate-50/50 p-6 text-slate-500 transition-all duration-300 hover:border-indigo-400 hover:bg-indigo-50 hover:text-indigo-600"
            :style="pageCreateCardStyle"
            @click="openCreateDialog">
            <div
              class="mb-4 flex h-12 w-12 items-center justify-center rounded-full border border-slate-200 bg-white shadow-sm">
              <Plus class="h-6 w-6" />
            </div>
            <span class="text-base font-bold">新增页面</span>
          </button>
        </div>
      </section>
    </div>

    <BaseDialog v-model="dialogVisible" title="新增页面" width="960px">
      <div class="space-y-6">
        <BaseInput v-model="form.title" label="标题" placeholder="请输入页面标题" required :error="errors.title" />

        <BaseInput v-model="form.summary" type="textarea" label="摘要说明" placeholder="简要概括此页面的核心职责" :rows="2" />

        <div class="space-y-1.5 border-t border-slate-100 pt-2">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <label class="ml-1 text-sm font-semibold text-slate-700">
              页面代码
              <span class="text-red-500">*</span>
            </label>
            <div class="flex items-center gap-2">
              <span class="text-[11px] font-bold uppercase tracking-widest text-slate-400">编辑器主题</span>
              <button v-for="option in themeOptions" :key="option.value" type="button"
                class="rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors" :class="createEditorTheme === option.value
                  ? 'border-fuchsia-400 bg-fuchsia-500 text-white'
                  : 'border-slate-200 bg-white text-slate-600 hover:border-slate-400'"
                @click="createEditorTheme = option.value">
                {{ option.label }}
              </button>
            </div>
          </div>
          <MonacoCodeEditor v-model="form.page_content" language="vue" :theme="createEditorTheme" :auto-save-delay="0"
            height="320px" :completion-config="{ includeDefault: true }" />
          <p v-if="errors.page_content" class="ml-1 mt-0.5 text-xs text-red-500">{{ errors.page_content }}</p>
        </div>
      </div>
      <template #footer>
        <BaseButton variant="ghost" @click="dialogVisible = false">取消</BaseButton>
        <BaseButton variant="primary" :loading="saving" @click="handleCreate">确 认 注入</BaseButton>
      </template>
    </BaseDialog>

    <PageCopyToProjectDialog
      v-model="pageCopyDialogVisible"
      :page="copyingPage"
      :workspace-id="workspaceId"
      :current-project-id="projectId"
      :loading="pageCopySaving"
      @submit="handlePageCopySubmit"
    />

    <PageBatchCopyToProjectDialog
      v-model="batchCopyDialogVisible"
      :pages="batchCopyPages"
      :workspace-id="workspaceId"
      :current-project-id="projectId"
      :loading="batchActionPending === 'copy'"
      @submit="handleBatchCopySubmit"
    />

    <ArchivedPagesDialog v-model="archivedPagesDialogVisible" :project-id="projectId"
      :screenshot-aspect-ratio="projectScreenshotAspectRatio" />

    <ProjectIdentityDialog v-model="projectIdentityDialogVisible" :project="projectDetails"
      :loading="projectIdentitySaving" @submit="handleProjectIdentityUpdate" />

    <ProjectPresentationConfigDialog v-model="presentationConfigDialogVisible" :project="projectDetails"
      :workspace-id="workspaceId" :default-theme-key="workspaceQuery.data.value?.default_theme_key ?? null"
      :loading="presentationConfigSaving" @save="handlePresentationConfigSave" />

    <ProjectRouteConfigDialog v-model="routeConfigDialogVisible" :project="projectDetails" :loading="routeSaving"
      @save="handleRouteSave" />

    <ProjectBuildDialog v-model="projectBuildDialogVisible" :history="buildHistory"
      :history-loading="buildHistoryQuery.isFetching.value" :latest-job="latestBuildJob"
      :latest-job-id="latestBuildJob?.id ?? null" :default-base-url="latestBuildJob?.base_url ?? './'"
      :loading="projectBuildSubmitting" @refresh="handleBuildHistoryRefresh" @download="handleBuildArtifactDownload"
      @open="handleBuildArtifactOpen" @submit="handleProjectBuildSubmit" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import type { Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import {
  Archive,
  ArrowLeft,
  Camera,
  Check,
  Copy,
  Expand,
  Hammer,
  Layout,
  ListPlus,
  LoaderCircle,
  Maximize2,
  Minimize2,
  Play,
  Plus,
  RefreshCw,
  Route as RouteIcon,
  RouteOff,
  SlidersHorizontal,
  Square,
  SquarePen,
  X,
} from 'lucide-vue-next'

import {
  createProjectBuildJob,
  downloadProjectBuildArtifact,
  getLatestProjectBuildJob,
  getProjectBuildJob,
  listProjectBuildJobs,
} from '@/api/builds'
import {
  copyPageToProject,
  createPage,
  getProject,
  getProjectRoutes,
  getWorkspace,
  listPages,
  replaceProjectRoutes,
  savePageScreenshot,
  updatePage,
  updateProject,
} from '@/api/catalog'
import { createProjectPreviewArtifact } from '@/api/preview'
import { getErrorMessage } from '@/api/http'
import MonacoCodeEditor from '@/components/editor/MonacoCodeEditor.vue'
import PageTitleBar from '@/components/layout/PageTitleBar.vue'
import ArchivedPagesDialog from '@/components/page/ArchivedPagesDialog.vue'
import PageBatchCopyToProjectDialog from '@/components/page/PageBatchCopyToProjectDialog.vue'
import PageCopyToProjectDialog from '@/components/page/PageCopyToProjectDialog.vue'
import ProjectBuildDialog from '@/components/project/ProjectBuildDialog.vue'
import ProjectIdentityDialog from '@/components/project/ProjectIdentityDialog.vue'
import ProjectPresentationConfigDialog from '@/components/project/ProjectPresentationConfigDialog.vue'
import ProjectRouteConfigDialog from '@/components/project/ProjectRouteConfigDialog.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import type { EditorThemeMode } from '@/types/monaco'
import type {
  PageCopyToProjectPayload,
  PageFileType,
  PageItem,
  ProjectBuildJob,
  ProjectMenuMode,
  ProjectRouteBinding,
  ProjectRouteItemWrite,
} from '@/types/api'
import { Message, createConfirm } from '@/utils/message'
import { getDefaultEditorTheme } from '@/utils/monaco'
import { canDownloadProjectBuildArtifact, canOpenProjectBuildArtifact } from '@/utils/project-build'
import { appendRootPageRoute, mapRouteTreeToWriteItems, normalizeProjectRouteOrders } from '@/utils/project-route'
import { buildPageDetailPath, buildWorkspaceHomePath } from '@/utils/workspace-routes'

interface RoutedPageEntry {
  key: string
  page: PageItem
  routePath: string
  routeOrderKey: number[]
  duplicateIndex: number
  duplicateTotal: number
  isDuplicate: boolean
}

interface AgentProjectPagesMutationDetail {
  workspaceId?: number | null
  projectId?: number | null
  pageId?: number | null
  componentId?: number | null
  toolName?: string
  result?: unknown
}

type PageBatchScope = 'routed' | 'unrouted'
type PageBatchAction = 'add-route' | 'remove-route' | 'screenshot' | 'archive' | 'copy'
type PageCardSize = 'compact' | 'standard' | 'large' | 'huge'

interface PageCardSizeOption {
  value: PageCardSize
  label: string
  minWidth: number
  icon: Component
}

const PAGE_CARD_SIZE_STORAGE_KEY = 'web-presentation:pages-view:preview-card-size'
const pageCardSizeOptions: PageCardSizeOption[] = [
  { value: 'compact', label: '紧凑', minWidth: 200, icon: Minimize2 },
  { value: 'standard', label: '标准', minWidth: 240, icon: Square },
  { value: 'large', label: '宽大', minWidth: 320, icon: Maximize2 },
  { value: 'huge', label: '超大', minWidth: 520, icon: Expand },
]

const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()

const workspaceId = computed(() => parseInt(route.params.workspaceId as string, 10))
const projectId = computed(() => parseInt(route.params.projectId as string, 10))

const query = useQuery(
  computed(() => ({
    queryKey: ['pages-by-project', projectId.value, 'active'],
    queryFn: () => listPages({ page: 1, page_size: 100, project_id: projectId.value, status: 'active' }),
    enabled: !!projectId.value,
  })),
)

const projectQuery = useQuery(
  computed(() => ({
    queryKey: ['project', projectId.value],
    queryFn: () => getProject(projectId.value),
    enabled: !!projectId.value,
  })),
)

const workspaceQuery = useQuery(
  computed(() => ({
    queryKey: ['workspace', workspaceId.value],
    queryFn: () => getWorkspace(workspaceId.value),
    enabled: !!workspaceId.value,
  })),
)

const projectDetails = computed(() => projectQuery.data.value ?? null)
const projectScreenshotAspectRatio = computed(() => {
  const width = Number(projectDetails.value?.page_width ?? 0)
  const height = Number(projectDetails.value?.page_height ?? 0)
  return width > 0 && height > 0 ? `${width} / ${height}` : '16 / 9'
})
const pageCardSize = ref<PageCardSize>(readStoredPageCardSize())
const currentPageCardSizeOption = computed(() => {
  return pageCardSizeOptions.find(option => option.value === pageCardSize.value) ?? pageCardSizeOptions[1]
})
const pageCardGridStyle = computed(() => ({
  gridTemplateColumns: `repeat(auto-fill, minmax(${currentPageCardSizeOption.value.minWidth}px, 1fr))`,
}))
const pageCreateCardStyle = computed(() => ({
  minHeight: `${Math.round(currentPageCardSizeOption.value.minWidth * 0.82)}px`,
}))
const pages = computed<PageItem[]>(() => query.data.value?.items ?? [])
const routedPageEntries = computed<RoutedPageEntry[]>(() => {
  return pages.value
    .flatMap((page) => {
      const routeBindings = getSortedRouteBindings(page)
      const duplicateTotal = routeBindings.length

      return routeBindings.map((binding, index) => ({
        key: `${page.id}-${binding.route_id}-${binding.full_path}`,
        page,
        routePath: normalizeRoutePath(binding.full_path),
        routeOrderKey: getRouteBindingOrderKey(binding),
        duplicateIndex: index + 1,
        duplicateTotal,
        isDuplicate: duplicateTotal > 1,
      }))
    })
    .sort((left, right) => {
      const routeOrderCompare = compareNumberTuple(left.routeOrderKey, right.routeOrderKey)
      if (routeOrderCompare !== 0) {
        return routeOrderCompare
      }
      const routePathCompare = left.routePath.localeCompare(right.routePath, 'zh-CN')
      if (routePathCompare !== 0) {
        return routePathCompare
      }
      return left.page.title.localeCompare(right.page.title, 'zh-CN')
    })
})
const unroutedPages = computed<PageItem[]>(() => {
  return pages.value
    .filter((page) => getSortedRouteBindings(page).length === 0)
    .sort((left, right) => left.title.localeCompare(right.title, 'zh-CN'))
})
const routedPagesForBatch = computed<PageItem[]>(() => {
  const pageMap = new Map<number, PageItem>()
  routedPageEntries.value.forEach((entry) => {
    if (!pageMap.has(entry.page.id)) {
      pageMap.set(entry.page.id, entry.page)
    }
  })
  return [...pageMap.values()]
})
const selectedRoutedPages = computed<PageItem[]>(() => (
  routedPagesForBatch.value.filter(page => selectedRoutedPageIds.value.has(page.id))
))
const selectedUnroutedPages = computed<PageItem[]>(() => (
  unroutedPages.value.filter(page => selectedUnroutedPageIds.value.has(page.id))
))
const isAllRoutedSelected = computed(() => (
  routedPagesForBatch.value.length > 0
  && selectedRoutedPages.value.length === routedPagesForBatch.value.length
))
const isAllUnroutedSelected = computed(() => (
  unroutedPages.value.length > 0
  && selectedUnroutedPages.value.length === unroutedPages.value.length
))
const routedRefreshableScreenshotPages = computed<PageItem[]>(() => (
  routedPagesForBatch.value.filter(isRefreshableScreenshotPage)
))
const unroutedRefreshableScreenshotPages = computed<PageItem[]>(() => (
  unroutedPages.value.filter(isRefreshableScreenshotPage)
))
const routedRefreshableScreenshotCount = computed(() => routedRefreshableScreenshotPages.value.length)
const unroutedRefreshableScreenshotCount = computed(() => unroutedRefreshableScreenshotPages.value.length)

const previewLoading = ref(false)
const batchScreenshotRefreshing = ref(false)
const batchScreenshotRefreshScope = ref<PageBatchScope | null>(null)
const projectBuildDialogVisible = ref(false)
const projectBuildSubmitting = ref(false)
const projectIdentityDialogVisible = ref(false)
const presentationConfigDialogVisible = ref(false)
const routeConfigDialogVisible = ref(false)
const archivedPagesDialogVisible = ref(false)
const pageCopyDialogVisible = ref(false)
const batchCopyDialogVisible = ref(false)
const projectIdentitySaving = ref(false)
const presentationConfigSaving = ref(false)
const routeSaving = ref(false)
const pageCopySaving = ref(false)
const batchActionPending = ref<PageBatchAction | null>(null)
const pageRoutePendingId = ref<number | null>(null)
const archivingPageId = ref<number | null>(null)
const screenshotPendingPageId = ref<number | null>(null)
const copyingPage = ref<PageItem | null>(null)
const batchCopyPages = ref<PageItem[]>([])
const selectedRoutedPageIds = ref<Set<number>>(new Set())
const selectedUnroutedPageIds = ref<Set<number>>(new Set())

const latestBuildJobQuery = useQuery(
  computed(() => ({
    queryKey: ['project-build-latest', projectId.value],
    queryFn: () => getLatestProjectBuildJob(projectId.value),
    enabled: !!projectId.value,
  })),
)

const buildHistoryQuery = useQuery(
  computed(() => ({
    queryKey: ['project-build-history', projectId.value],
    queryFn: () => listProjectBuildJobs(projectId.value, 20),
    enabled: !!projectId.value && projectBuildDialogVisible.value,
  })),
)

const latestBuildJob = computed<ProjectBuildJob | null>(() => latestBuildJobQuery.data.value ?? null)
const buildHistory = computed(() => buildHistoryQuery.data.value ?? [])

const dialogVisible = ref(false)
const saving = ref(false)
const createEditorTheme = ref<EditorThemeMode>(getDefaultEditorTheme())

const form = reactive({
  page_content: '',
  file_type: 'vue' as PageFileType,
  title: '',
  summary: '',
})

const errors = reactive({
  page_content: '',
  title: '',
})

const themeOptions: Array<{ label: string; value: EditorThemeMode }> = [
  { label: '暗色', value: 'dark' },
  { label: '明亮', value: 'light' },
]

watch(pageCardSize, (nextSize) => {
  persistPageCardSize(nextSize)
})

const savePageMutation = useMutation({
  mutationFn: () =>
    createPage({
      page_content: form.page_content,
      file_type: form.file_type,
      title: form.title,
      summary: form.summary || null,
      status: 'active',
      workspace_id: workspaceId.value,
      project_id: projectId.value,
    }),
})

const archivePageMutation = useMutation({
  mutationFn: (pageId: number) => updatePage(pageId, { status: 'archived' }),
})

/**
 * 按页面路由绑定路径排序，供卡片分组和重复标记共同使用。
 * @param page 页面资源
 */
function getSortedRouteBindings(page: PageItem): ProjectRouteBinding[] {
  return [...(page.route_bindings ?? [])].sort((left, right) => {
    const routeOrderCompare = compareNumberTuple(getRouteBindingOrderKey(left), getRouteBindingOrderKey(right))
    if (routeOrderCompare !== 0) {
      return routeOrderCompare
    }
    return normalizeRoutePath(left.full_path).localeCompare(normalizeRoutePath(right.full_path), 'zh-CN')
  })
}

/**
 * 将路由绑定转换为可比较的树顺序，分组子路由先按父级排序，再按子节点排序。
 * @param binding 页面路由绑定
 */
function getRouteBindingOrderKey(binding: ProjectRouteBinding): number[] {
  const fallbackOrder = Number.MAX_SAFE_INTEGER
  const routeOrder = typeof binding.order === 'number' ? binding.order : fallbackOrder
  const parentOrder = typeof binding.parent_order === 'number' ? binding.parent_order : routeOrder
  return [parentOrder, routeOrder, binding.route_id]
}

/**
 * 比较数字元组，用于保持页面卡片与路由树顺序一致。
 * @param left 左侧顺序元组
 * @param right 右侧顺序元组
 */
function compareNumberTuple(left: number[], right: number[]): number {
  const length = Math.max(left.length, right.length)
  for (let index = 0; index < length; index += 1) {
    const diff = (left[index] ?? 0) - (right[index] ?? 0)
    if (diff !== 0) {
      return diff
    }
  }
  return 0
}

/**
 * 归一化路由展示路径，避免空路径破坏排序与展示。
 * @param path 后端返回的完整路径
 */
function normalizeRoutePath(path: string | null | undefined): string {
  const trimmedPath = String(path ?? '').trim()
  return trimmedPath || '/'
}

/**
 * 判断已加入路由分区的页面是否被选中。
 * @param pageId 页面 ID
 */
function isRoutedPageSelected(pageId: number): boolean {
  return selectedRoutedPageIds.value.has(pageId)
}

/**
 * 判断未加入路由分区的页面是否被选中。
 * @param pageId 页面 ID
 */
function isUnroutedPageSelected(pageId: number): boolean {
  return selectedUnroutedPageIds.value.has(pageId)
}

/**
 * 更新已加入路由分区单页选择状态。
 * @param pageId 页面 ID
 * @param event 勾选框事件
 */
function handleRoutedPageSelectionChange(pageId: number, event: Event): void {
  updateSelection(selectedRoutedPageIds, pageId, (event.target as HTMLInputElement).checked)
}

/**
 * 更新未加入路由分区单页选择状态。
 * @param pageId 页面 ID
 * @param event 勾选框事件
 */
function handleUnroutedPageSelectionChange(pageId: number, event: Event): void {
  updateSelection(selectedUnroutedPageIds, pageId, (event.target as HTMLInputElement).checked)
}

/**
 * 批量勾选或取消已加入路由分区页面。
 * @param event 勾选框事件
 */
function handleRoutedSelectAllChange(event: Event): void {
  selectedRoutedPageIds.value = (event.target as HTMLInputElement).checked
    ? new Set(routedPagesForBatch.value.map(page => page.id))
    : new Set()
}

/**
 * 批量勾选或取消未加入路由分区页面。
 * @param event 勾选框事件
 */
function handleUnroutedSelectAllChange(event: Event): void {
  selectedUnroutedPageIds.value = (event.target as HTMLInputElement).checked
    ? new Set(unroutedPages.value.map(page => page.id))
    : new Set()
}

function clearRoutedSelection(): void {
  selectedRoutedPageIds.value = new Set()
}

function clearUnroutedSelection(): void {
  selectedUnroutedPageIds.value = new Set()
}

/**
 * 设置页面预览卡片尺寸，并通过监听器持久化到浏览器缓存。
 * @param size 卡片尺寸档位
 */
function setPageCardSize(size: PageCardSize): void {
  pageCardSize.value = size
}

/**
 * 从浏览器缓存读取页面预览卡片尺寸偏好。
 */
function readStoredPageCardSize(): PageCardSize {
  if (typeof window === 'undefined') {
    return 'standard'
  }

  try {
    const storedSize = window.localStorage.getItem(PAGE_CARD_SIZE_STORAGE_KEY)
    return isPageCardSize(storedSize) ? storedSize : 'standard'
  } catch {
    return 'standard'
  }
}

/**
 * 把页面预览卡片尺寸写入浏览器缓存。
 * @param size 卡片尺寸档位
 */
function persistPageCardSize(size: PageCardSize): void {
  if (typeof window === 'undefined') {
    return
  }

  try {
    window.localStorage.setItem(PAGE_CARD_SIZE_STORAGE_KEY, size)
  } catch {
    // 浏览器隐私模式或容量限制下忽略缓存失败，不影响页面使用。
  }
}

/**
 * 判断缓存值是否为受支持的卡片尺寸档位。
 * @param value 待校验值
 */
function isPageCardSize(value: string | null): value is PageCardSize {
  return value === 'compact' || value === 'standard' || value === 'large' || value === 'huge'
}

/**
 * 判断页面截图是否缺失或已过期，且当前文件类型支持截图。
 * @param page 页面资源
 */
function isRefreshableScreenshotPage(page: PageItem): boolean {
  return page.file_type === 'vue' && (!page.screenshot_url || !page.screenshot_is_latest)
}

/**
 * 以不可变方式更新指定页面集合的选择状态。
 * @param selectionRef 选择集合 ref
 * @param pageId 页面 ID
 * @param checked 是否选中
 */
function updateSelection(selectionRef: { value: Set<number> }, pageId: number, checked: boolean): void {
  const nextSelection = new Set(selectionRef.value)
  if (checked) {
    nextSelection.add(pageId)
  } else {
    nextSelection.delete(pageId)
  }
  selectionRef.value = nextSelection
}

/**
 * 获取指定分区当前选中的页面集合。
 * @param scope 页面分区
 */
function getSelectedPagesByScope(scope: PageBatchScope): PageItem[] {
  return scope === 'routed' ? selectedRoutedPages.value : selectedUnroutedPages.value
}

/**
 * 获取指定分区需要刷新截图的页面集合。
 * @param scope 页面分区
 */
function getRefreshableScreenshotPagesByScope(scope: PageBatchScope): PageItem[] {
  return scope === 'routed' ? routedRefreshableScreenshotPages.value : unroutedRefreshableScreenshotPages.value
}

function openCreateDialog(): void {
  form.page_content = ''
  form.file_type = 'vue'
  form.title = ''
  form.summary = ''
  createEditorTheme.value = getDefaultEditorTheme()
  errors.page_content = ''
  errors.title = ''
  dialogVisible.value = true
}

async function handleCreate(): Promise<void> {
  let hasError = false
  if (!form.page_content.trim()) {
    errors.page_content = '请输入页面内容'
    hasError = true
  } else {
    errors.page_content = ''
  }
  if (!form.title.trim()) {
    errors.title = '请输入标题'
    hasError = true
  } else {
    errors.title = ''
  }
  if (hasError) {
    return
  }

  saving.value = true
  try {
    const newPage = await savePageMutation.mutateAsync()
    await queryClient.invalidateQueries({ queryKey: ['pages-by-project', projectId.value] })
    dialogVisible.value = false
    Message.success('页面节点注入成功。')
    goToPage(newPage.id)
  } catch (error) {
    Message.error(getErrorMessage(error, '注入失败。'))
  } finally {
    saving.value = false
  }
}

function goToPage(id: number): void {
  router.push(buildPageDetailPath(workspaceId.value, projectId.value, id))
}

/**
 * 返回当前项目所属工作空间首页。
 */
function goToWorkspaceHome(): void {
  void router.push(buildWorkspaceHomePath(workspaceId.value))
}

/**
 * 接收智能体项目页面或路由变更事件，刷新列表和项目头部信息。
 */
function handleGlobalAgentProjectPagesUpdated(event: Event): void {
  const detail = (event as CustomEvent<AgentProjectPagesMutationDetail>).detail
  if (detail?.workspaceId && detail.workspaceId !== workspaceId.value) return
  if (detail?.projectId && detail.projectId !== projectId.value) return
  void refreshProjectPagesAfterAgentMutation(detail)
}

/**
 * 接收智能体项目配置变更事件，刷新当前项目详情。
 */
function handleGlobalAgentProjectUpdated(event: Event): void {
  const detail = (event as CustomEvent<AgentProjectPagesMutationDetail>).detail
  if (detail?.workspaceId && detail.workspaceId !== workspaceId.value) return
  if (detail?.projectId && detail.projectId !== projectId.value) return
  void refreshProjectAfterAgentMutation()
}

/**
 * 批量刷新页面列表相关查询；创建页成功时直接进入新页面详情。
 * @param detail 智能体工具写回事件详情
 */
async function refreshProjectPagesAfterAgentMutation(detail?: AgentProjectPagesMutationDetail): Promise<void> {
  await Promise.all([
    query.refetch(),
    projectQuery.refetch(),
    queryClient.invalidateQueries({ queryKey: ['pages-by-project', projectId.value] }),
    queryClient.invalidateQueries({ queryKey: ['project', projectId.value] }),
  ])
  if (detail?.toolName === 'create_project_page' && detail.pageId) {
    goToPage(detail.pageId)
  }
}

/**
 * 刷新项目详情查询，供项目级智能体写入后同步页面头部和配置弹窗。
 */
async function refreshProjectAfterAgentMutation(): Promise<void> {
  await Promise.all([
    projectQuery.refetch(),
    queryClient.invalidateQueries({ queryKey: ['project', projectId.value] }),
  ])
}

/**
 * 打开页面复制到项目弹窗。
 * @param page 待复制页面
 */
function openPageCopyDialog(page: PageItem): void {
  copyingPage.value = page
  pageCopyDialogVisible.value = true
}

/**
 * 调用后端复制页面，成功后跳转目标项目的新页面详情。
 * @param payload 页面复制配置
 */
async function handlePageCopySubmit(payload: PageCopyToProjectPayload): Promise<void> {
  if (!copyingPage.value) {
    return
  }

  pageCopySaving.value = true
  try {
    const copiedPage = await copyPageToProject(copyingPage.value.id, payload)
    const nextProjectId = copiedPage.project_id ?? payload.target_project_id
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['pages-by-project', projectId.value] }),
      queryClient.invalidateQueries({ queryKey: ['pages-by-project', nextProjectId] }),
      queryClient.invalidateQueries({ queryKey: ['project', nextProjectId] }),
    ])
    pageCopyDialogVisible.value = false
    copyingPage.value = null
    Message.success('页面已复制到目标项目。')
    void router.push(buildPageDetailPath(workspaceId.value, nextProjectId, copiedPage.id))
  } catch (error) {
    Message.error(getErrorMessage(error, '复制页面失败。'))
  } finally {
    pageCopySaving.value = false
  }
}

/**
 * 打开批量复制弹窗，复制范围取当前分区已选页面。
 * @param scope 页面分区
 */
function openBatchCopyDialog(scope: PageBatchScope): void {
  const selectedPages = getSelectedPagesByScope(scope)
  if (selectedPages.length === 0) {
    Message.warning('请先选择页面。')
    return
  }
  batchCopyPages.value = selectedPages
  batchCopyDialogVisible.value = true
}

/**
 * 批量调用页面复制接口；标题、摘要和路由片段由后端按源页面和新编码处理。
 * @param payload 批量复制配置
 */
async function handleBatchCopySubmit(payload: PageCopyToProjectPayload): Promise<void> {
  if (batchCopyPages.value.length === 0 || batchActionPending.value !== null) {
    return
  }

  batchActionPending.value = 'copy'
  let succeededCount = 0
  let firstErrorMessage = ''
  try {
    for (const page of batchCopyPages.value) {
      try {
        await copyPageToProject(page.id, {
          target_project_id: payload.target_project_id,
          route_placement: payload.route_placement ?? 'none',
          parent_route_id: payload.parent_route_id ?? null,
          route: null,
        })
        succeededCount += 1
      } catch (error) {
        firstErrorMessage ||= getErrorMessage(error, `复制「${page.title}」失败。`)
      }
    }

    await refreshPageListCaches(payload.target_project_id)
    batchCopyDialogVisible.value = false
    batchCopyPages.value = []
    clearRoutedSelection()
    clearUnroutedSelection()
    showBatchResultMessage('复制', succeededCount, firstErrorMessage)
  } finally {
    batchActionPending.value = null
  }
}

/**
 * 将未加入路由的已选页面批量追加为顶层路由。
 */
async function handleBatchAddToRoute(): Promise<void> {
  if (!projectDetails.value || selectedUnroutedPages.value.length === 0 || batchActionPending.value !== null) {
    return
  }

  batchActionPending.value = 'add-route'
  try {
    const routeTree = await getProjectRoutes(projectDetails.value.id)
    let nextRoutes = mapRouteTreeToWriteItems(routeTree.routes)
    selectedUnroutedPages.value.forEach((page) => {
      nextRoutes = appendRootPageRoute(nextRoutes, page)
    })
    await replaceProjectRoutes(projectDetails.value.id, { routes: nextRoutes })
    await refreshPageListCaches()
    Message.success(`已将 ${selectedUnroutedPages.value.length} 个页面加入项目路由。`)
    clearUnroutedSelection()
  } catch (error) {
    Message.error(getErrorMessage(error, '批量加入路由失败。'))
  } finally {
    batchActionPending.value = null
  }
}

/**
 * 将已加入路由的选中页面从项目路由树中移出。
 */
async function handleBatchRemoveFromRoute(): Promise<void> {
  if (!projectDetails.value || selectedRoutedPages.value.length === 0 || batchActionPending.value !== null) {
    return
  }

  const confirmed = await createConfirm(
    `确定将选中的 ${selectedRoutedPages.value.length} 个页面移出项目路由吗？页面本身不会被归档。`,
    '批量移出路由',
  )
  if (!confirmed) {
    return
  }

  batchActionPending.value = 'remove-route'
  try {
    const selectedPageIds = new Set(selectedRoutedPages.value.map(page => page.id))
    const routeTree = await getProjectRoutes(projectDetails.value.id)
    const nextRoutes = removePagesFromProjectRoutes(mapRouteTreeToWriteItems(routeTree.routes), selectedPageIds)
    await replaceProjectRoutes(projectDetails.value.id, { routes: nextRoutes })
    await refreshPageListCaches()
    Message.success(`已将 ${selectedPageIds.size} 个页面移出项目路由。`)
    clearRoutedSelection()
  } catch (error) {
    Message.error(getErrorMessage(error, '批量移出路由失败。'))
  } finally {
    batchActionPending.value = null
  }
}

/**
 * 为当前分区已选页面逐个刷新截图。
 * @param scope 页面分区
 */
async function handleBatchSaveScreenshots(scope: PageBatchScope): Promise<void> {
  const selectedPages = getSelectedPagesByScope(scope)
  if (selectedPages.length === 0 || batchActionPending.value !== null) {
    return
  }

  batchActionPending.value = 'screenshot'
  let succeededCount = 0
  let firstErrorMessage = ''
  try {
    for (const page of selectedPages) {
      try {
        await savePageScreenshot(page.id)
        succeededCount += 1
      } catch (error) {
        firstErrorMessage ||= getErrorMessage(error, `更新「${page.title}」截图失败。`)
      }
    }
    await refreshPageListCaches()
    showBatchResultMessage('截图', succeededCount, firstErrorMessage)
  } finally {
    batchActionPending.value = null
  }
}

/**
 * 为指定页面分区中缺失或过期的页面批量刷新截图。
 * @param scope 页面分区
 */
async function handleRefreshSectionPageScreenshots(scope: PageBatchScope): Promise<void> {
  const targetPages = getRefreshableScreenshotPagesByScope(scope)
  if (targetPages.length === 0 || batchScreenshotRefreshing.value) {
    return
  }

  batchScreenshotRefreshing.value = true
  batchScreenshotRefreshScope.value = scope
  let succeededCount = 0
  let firstErrorMessage = ''
  try {
    for (const page of targetPages) {
      try {
        await savePageScreenshot(page.id)
        succeededCount += 1
      } catch (error) {
        firstErrorMessage ||= getErrorMessage(error, `更新「${page.title}」截图失败。`)
      }
    }
    await refreshPageListCaches()
    showBatchResultMessage('截图', succeededCount, firstErrorMessage)
  } finally {
    batchScreenshotRefreshing.value = false
    batchScreenshotRefreshScope.value = null
  }
}

/**
 * 批量归档当前分区已选页面。
 * @param scope 页面分区
 */
async function handleBatchArchivePages(scope: PageBatchScope): Promise<void> {
  const selectedPages = getSelectedPagesByScope(scope)
  if (selectedPages.length === 0 || batchActionPending.value !== null) {
    return
  }

  const confirmed = await createConfirm(`确定归档选中的 ${selectedPages.length} 个页面吗？`, '批量归档页面')
  if (!confirmed) {
    return
  }

  batchActionPending.value = 'archive'
  let succeededCount = 0
  let firstErrorMessage = ''
  try {
    for (const page of selectedPages) {
      try {
        await updatePage(page.id, { status: 'archived' })
        succeededCount += 1
      } catch (error) {
        firstErrorMessage ||= getErrorMessage(error, `归档「${page.title}」失败。`)
      }
    }
    await refreshPageListCaches()
    clearSelectionByScope(scope)
    showBatchResultMessage('归档', succeededCount, firstErrorMessage)
  } finally {
    batchActionPending.value = null
  }
}

/**
 * 从路由草稿中移除所有绑定指定页面的节点，并丢弃被清空的分组。
 * @param routeItems 当前路由草稿
 * @param pageIds 待移出路由的页面 ID 集合
 */
function removePagesFromProjectRoutes(routeItems: ProjectRouteItemWrite[], pageIds: Set<number>): ProjectRouteItemWrite[] {
  const nextRoutes: ProjectRouteItemWrite[] = []
  routeItems.forEach((routeItem) => {
    if (routeItem.route_type === 'group') {
      const children = (routeItem.children ?? []).filter(child => !pageIds.has(child.page_id))
      if (children.length > 0) {
        nextRoutes.push({ ...routeItem, children })
      }
      return
    }
    if (routeItem.page_id && !pageIds.has(routeItem.page_id)) {
      nextRoutes.push(routeItem)
    }
  })
  return normalizeProjectRouteOrders(nextRoutes)
}

/**
 * 按分区清空选择状态。
 * @param scope 页面分区
 */
function clearSelectionByScope(scope: PageBatchScope): void {
  if (scope === 'routed') {
    clearRoutedSelection()
    return
  }
  clearUnroutedSelection()
}

/**
 * 刷新当前项目页面缓存，并在复制场景下刷新目标项目页面缓存。
 * @param targetProjectId 可选目标项目 ID
 */
async function refreshPageListCaches(targetProjectId?: number): Promise<void> {
  const tasks = [
    queryClient.invalidateQueries({ queryKey: ['pages-by-project', projectId.value] }),
    queryClient.invalidateQueries({ queryKey: ['project', projectId.value] }),
  ]
  if (targetProjectId && targetProjectId !== projectId.value) {
    tasks.push(
      queryClient.invalidateQueries({ queryKey: ['pages-by-project', targetProjectId] }),
      queryClient.invalidateQueries({ queryKey: ['project', targetProjectId] }),
    )
  }
  await Promise.all(tasks)
}

/**
 * 统一展示批量操作结果。
 * @param actionLabel 操作名称
 * @param succeededCount 成功数量
 * @param firstErrorMessage 首个失败原因
 */
function showBatchResultMessage(actionLabel: string, succeededCount: number, firstErrorMessage: string): void {
  if (firstErrorMessage) {
    Message.warning(`批量${actionLabel}完成 ${succeededCount} 个，存在失败：${firstErrorMessage}`)
    return
  }
  Message.success(`批量${actionLabel}完成 ${succeededCount} 个页面。`)
}

/**
 * 将页面移入归档列表。
 * @param page 待归档页面
 */
async function handleArchivePage(page: PageItem): Promise<void> {
  const confirmed = await createConfirm(`归档后页面将从当前列表移入“归档页面”，确定归档「${page.title}」吗？`, '归档页面')
  if (!confirmed || archivingPageId.value === page.id) {
    return
  }

  archivingPageId.value = page.id
  try {
    await archivePageMutation.mutateAsync(page.id)
    await queryClient.invalidateQueries({ queryKey: ['pages-by-project', projectId.value] })
    Message.success('页面已归档。')
  } catch (error) {
    Message.error(getErrorMessage(error, '归档页面失败。'))
  } finally {
    archivingPageId.value = null
  }
}

/**
 * 触发后端为指定页面重新生成截图，并在完成后刷新列表中的截图地址。
 * @param page 待截图的页面资源
 */
async function handleSavePageScreenshot(page: PageItem): Promise<void> {
  if (screenshotPendingPageId.value !== null || batchScreenshotRefreshing.value) {
    return
  }

  screenshotPendingPageId.value = page.id
  try {
    await savePageScreenshot(page.id)
    await queryClient.invalidateQueries({ queryKey: ['pages-by-project', projectId.value] })
    Message.success(`「${page.title}」截图已更新。`)
  } catch (error) {
    Message.error(getErrorMessage(error, '更新页面截图失败。'))
  } finally {
    screenshotPendingPageId.value = null
  }
}

/**
 * 打开项目构建中心弹窗。
 */
function openBuildDialog(): void {
  projectBuildDialogVisible.value = true
}

/**
 * 打开项目名称与描述编辑弹窗。
 */
function openProjectIdentityDialog(): void {
  projectIdentityDialogVisible.value = true
}

/**
 * 打开项目展示配置弹窗。
 */
function openPresentationConfigDialog(): void {
  presentationConfigDialogVisible.value = true
}

/**
 * 打开项目路由配置弹窗。
 */
function openRouteConfigDialog(): void {
  routeConfigDialogVisible.value = true
}

/**
 * 从页面卡片直接追加顶层页面路由。
 * @param page 待加入路由的页面
 */
async function handleAddPageToRoute(page: PageItem): Promise<void> {
  if (!projectDetails.value || pageRoutePendingId.value === page.id) {
    return
  }

  pageRoutePendingId.value = page.id
  try {
    const routeTree = await getProjectRoutes(projectDetails.value.id)
    const nextRoutes = appendRootPageRoute(mapRouteTreeToWriteItems(routeTree.routes), page)
    await replaceProjectRoutes(projectDetails.value.id, { routes: nextRoutes })
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['pages-by-project', projectId.value] }),
      queryClient.invalidateQueries({ queryKey: ['project', projectId.value] }),
    ])
    Message.success(`已将「${page.title}」加入项目路由。`)
  } catch (error) {
    Message.error(getErrorMessage(error, '加入项目路由失败。'))
  } finally {
    pageRoutePendingId.value = null
  }
}

/**
 * 更新项目名称与描述，并同步刷新项目页头信息与项目列表缓存。
 * @param payload 项目基础信息
 */
async function handleProjectIdentityUpdate(payload: { name: string; description: string | null }): Promise<void> {
  if (!projectDetails.value) {
    return
  }

  projectIdentitySaving.value = true
  try {
    await updateProject(projectDetails.value.id, payload)
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['project', projectId.value] }),
      queryClient.invalidateQueries({ queryKey: ['projects-by-ws', workspaceId.value] }),
    ])
    projectIdentityDialogVisible.value = false
    Message.success('项目基础信息已同步。')
  } catch (error) {
    Message.error(getErrorMessage(error, '更新项目基础信息失败。'))
  } finally {
    projectIdentitySaving.value = false
  }
}

/**
 * 保存项目展示配置。
 * @param payload 项目展示配置
 */
async function handlePresentationConfigSave(payload: {
  page_width: number
  page_height: number
  base_font_size: string
  icon_default_stroke_width: number
  show_pdf_export_button: boolean
  menu_mode: ProjectMenuMode
  theme_key: string | null
  style_spec_markdown: string
}): Promise<void> {
  if (!projectDetails.value) {
    return
  }

  presentationConfigSaving.value = true
  try {
    await updateProject(projectDetails.value.id, payload)
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['project', projectId.value] }),
      queryClient.invalidateQueries({ queryKey: ['projects-by-ws', workspaceId.value] }),
    ])
    presentationConfigDialogVisible.value = false
    Message.success('项目展示配置已保存。')
  } catch (error) {
    Message.error(getErrorMessage(error, '保存项目展示配置失败。'))
  } finally {
    presentationConfigSaving.value = false
  }
}

/**
 * 覆盖保存项目路由树，并刷新页面列表中的路由绑定状态。
 * @param payload 最新路由树
 */
async function handleRouteSave(payload: { routes: ProjectRouteItemWrite[] }): Promise<void> {
  if (!projectDetails.value) {
    return
  }

  routeSaving.value = true
  try {
    await replaceProjectRoutes(projectDetails.value.id, { routes: payload.routes })
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['pages-by-project', projectId.value] }),
      queryClient.invalidateQueries({ queryKey: ['project', projectId.value] }),
    ])
    routeConfigDialogVisible.value = false
    Message.success('项目路由已保存。')
  } catch (error) {
    Message.error(getErrorMessage(error, '保存项目路由失败。'))
  } finally {
    routeSaving.value = false
  }
}

/**
 * 生成当前项目的整项目预览链接，并在新标签页打开。
 */
async function handlePreviewProject(): Promise<void> {
  if (!projectDetails.value) {
    return
  }

  previewLoading.value = true
  try {
    const res = await createProjectPreviewArtifact(projectDetails.value.id)
    window.open(res.preview_url, '_blank')
  } catch (error) {
    Message.error(getErrorMessage(error, '生成整项目预览失败。'))
  } finally {
    previewLoading.value = false
  }
}

/**
 * 刷新最近构建状态与构建历史列表。
 */
async function handleBuildHistoryRefresh(): Promise<void> {
  await Promise.all([
    latestBuildJobQuery.refetch(),
    buildHistoryQuery.refetch(),
  ])
}

/**
 * 下载指定构建任务的 ZIP 产物。
 * @param job 构建任务
 */
async function handleBuildArtifactDownload(job: ProjectBuildJob): Promise<void> {
  if (!projectDetails.value || !canDownloadProjectBuildArtifact(job)) {
    return
  }

  try {
    await downloadProjectBuildArtifact(projectDetails.value.id, job.id)
  } catch (error) {
    Message.error(getErrorMessage(error, '下载构建产物失败。'))
  }
}

/**
 * 在新标签页打开指定构建任务的公开产物入口。
 * @param job 构建任务
 */
function handleBuildArtifactOpen(job: ProjectBuildJob): void {
  if (!canOpenProjectBuildArtifact(job) || !job.artifact_proxy_url) {
    return
  }

  window.open(job.artifact_proxy_url, '_blank', 'noopener,noreferrer')
}

/**
 * 提交整项目构建任务，并回读一次任务详情。
 * @param payload 构建参数
 */
async function handleProjectBuildSubmit(payload: { base_url: string }): Promise<void> {
  if (!projectDetails.value) {
    return
  }

  projectBuildSubmitting.value = true
  try {
    const createdJob = await createProjectBuildJob(projectDetails.value.id, payload)
    const latestJob = await getProjectBuildJob(createdJob.id)
    queryClient.setQueryData(['project-build-latest', projectId.value], latestJob)
    queryClient.setQueryData<ProjectBuildJob[]>(['project-build-history', projectId.value], (previous) => {
      const nextItems = [latestJob, ...(previous ?? []).filter((item) => item.id !== latestJob.id)]
      return nextItems.slice(0, 20)
    })
    projectBuildDialogVisible.value = false
    Message.success('构建任务已提交。')
  } catch (error) {
    Message.error(getErrorMessage(error, '提交构建任务失败。'))
  } finally {
    projectBuildSubmitting.value = false
  }
}

onMounted(() => {
  window.addEventListener('agent:project-pages-updated', handleGlobalAgentProjectPagesUpdated)
  window.addEventListener('agent:project-updated', handleGlobalAgentProjectUpdated)
})

onUnmounted(() => {
  window.removeEventListener('agent:project-pages-updated', handleGlobalAgentProjectPagesUpdated)
  window.removeEventListener('agent:project-updated', handleGlobalAgentProjectUpdated)
})
</script>

<style scoped>
.page-card-size-control {
  display: inline-flex;
  align-items: center;
  gap: 0.125rem;
  border-radius: 0.625rem;
  border: 1px solid rgb(226 232 240);
  background: rgb(248 250 252);
  padding: 0.125rem;
}

.page-card-size-button {
  display: inline-flex;
  height: 1.875rem;
  width: 1.875rem;
  align-items: center;
  justify-content: center;
  border-radius: 0.5rem;
  color: rgb(100 116 139);
  transition: all 0.18s ease;
}

.page-card-size-button:hover,
.page-card-size-button-active {
  background: white;
  color: rgb(79 70 229);
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.08);
}

.page-card-size-button:focus-visible {
  outline: 2px solid rgb(129 140 248);
  outline-offset: 2px;
}

:deep(.project-build-action) {
  border-color: rgb(99 102 241);
  background: linear-gradient(135deg, rgb(79 70 229), rgb(14 165 233));
  box-shadow: 0 8px 18px rgb(79 70 229 / 0.22);
}

:deep(.project-build-action:hover) {
  border-color: rgb(67 56 202);
  box-shadow: 0 10px 22px rgb(79 70 229 / 0.28);
}

.page-card-action {
  display: inline-flex;
  height: 1.875rem;
  width: 1.875rem;
  align-items: center;
  justify-content: center;
  border-radius: 0.5rem;
  border: 1px solid rgb(226 232 240);
  background: rgb(255 255 255 / 0.95);
  color: rgb(71 85 105);
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.08);
  transition: all 0.2s ease;
}

.page-card-action:hover {
  border-color: rgb(199 210 254);
  background: rgb(238 242 255);
  color: rgb(79 70 229);
}

.page-card-action:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.page-card-select {
  display: inline-flex;
  height: 1.5rem;
  width: 1.5rem;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  border: 1px solid rgb(203 213 225);
  background: rgb(255 255 255 / 0.95);
  color: rgb(100 116 139);
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.08);
  backdrop-filter: blur(6px);
  cursor: pointer;
  transition: all 0.18s ease;
}

.page-card-select:hover,
.page-card-select-active {
  border-color: rgb(129 140 248);
  background: rgb(238 242 255 / 0.96);
  color: rgb(79 70 229);
  opacity: 1;
  transform: translateY(-1px);
}

.page-card-select-active {
  background: rgb(79 70 229 / 0.96);
  color: white;
}

.page-card-select-box {
  display: inline-flex;
  height: 0.875rem;
  width: 0.875rem;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  border: 1px solid currentColor;
}

.page-card-topbar {
  pointer-events: none;
  position: absolute;
  inset: 0.5rem 0.5rem auto;
  z-index: 20;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
  opacity: 0;
  transform: translateY(-0.25rem);
  transition: all 0.2s ease;
}

.group\/card:hover .page-card-topbar,
.page-card-topbar-active {
  pointer-events: auto;
  opacity: 1;
  transform: translateY(0);
}

.page-card-topbar-end {
  justify-content: flex-end;
}

.page-card-route-path {
  display: inline-flex;
  min-width: 0;
  max-width: calc(100% - 2rem);
  min-height: 1.5rem;
  align-items: center;
  gap: 0.375rem;
  border-radius: 9999px;
  border: 1px solid rgb(167 243 208);
  background: rgb(255 255 255 / 0.95);
  padding: 0.25rem 0.5rem;
  font-size: 0.625rem;
  font-weight: 700;
  color: rgb(4 120 87);
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.08);
  backdrop-filter: blur(6px);
}

.page-card-top-actions {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 0.375rem;
}

.page-card-stale-badge {
  display: inline-flex;
  min-height: 1.5rem;
  align-items: center;
  border-radius: 9999px;
  border: 1px solid rgb(253 230 138);
  background: rgb(255 251 235 / 0.95);
  padding: 0.25rem 0.5rem;
  font-size: 0.625rem;
  font-weight: 700;
  color: rgb(180 83 9);
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.08);
  backdrop-filter: blur(6px);
}

.batch-select-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  min-height: 2.125rem;
  border-radius: 9999px;
  border: 1px solid rgb(226 232 240);
  background: white;
  padding: 0.35rem 0.75rem 0.35rem 0.5rem;
  font-size: 0.75rem;
  font-weight: 700;
  color: rgb(71 85 105);
  cursor: pointer;
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.06);
  transition: all 0.18s ease;
}

.batch-select-toggle:hover,
.batch-select-toggle-active {
  border-color: rgb(199 210 254);
  background: rgb(238 242 255);
  color: rgb(79 70 229);
}

.batch-select-box {
  display: inline-flex;
  height: 1rem;
  width: 1rem;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  border: 1px solid rgb(148 163 184);
  background: white;
  color: white;
}

.batch-select-toggle-active .batch-select-box {
  border-color: rgb(79 70 229);
  background: rgb(79 70 229);
}

.batch-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  border-radius: 9999px;
  border: 1px solid rgb(226 232 240);
  background: white;
  padding: 0.3rem;
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.06);
}

.batch-toolbar-count {
  padding: 0 0.4rem;
  font-size: 0.75rem;
  font-weight: 700;
  color: rgb(100 116 139);
}

.batch-toolbar-action,
.batch-toolbar-icon {
  display: inline-flex;
  height: 2rem;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
  border-radius: 0.5rem;
  padding: 0 0.55rem;
  font-size: 0.75rem;
  font-weight: 700;
  color: rgb(71 85 105);
  transition: all 0.2s ease;
}

.batch-toolbar-icon {
  width: 2rem;
  padding: 0;
}

.batch-toolbar-action:hover,
.batch-toolbar-icon:hover {
  background: rgb(238 242 255);
  color: rgb(79 70 229);
}

.batch-toolbar-action:disabled,
.batch-toolbar-icon:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.project-identity-action {
  display: inline-flex;
  height: 1.625rem;
  width: 1.625rem;
  align-items: center;
  justify-content: center;
  border-radius: 0.5rem;
  border: 1px solid rgb(226 232 240);
  background: rgb(248 250 252);
  color: rgb(100 116 139);
  transition: all 0.2s ease;
}

.project-identity-action:hover {
  border-color: rgb(199 210 254);
  background: rgb(238 242 255);
  color: rgb(79 70 229);
}
</style>

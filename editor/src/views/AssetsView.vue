<!-- 文件功能：提供工作空间级资源库页面，承载资源筛选、视觉预览、详情编辑、引用检查与归档删除。 -->
<template>
  <div data-testid="assets-view" class="flex h-full min-h-0 flex-col gap-4">
    <PageTitleBar class="shrink-0" :title="workspaceTitle">
      <template #actions>
        <BaseButton variant="ghost" :disabled="!workspaceId || uploading" @click="openUploadForm">
          <Upload class="h-3.5 w-3.5" />
          {{ uploading ? '上传中' : '上传资源' }}
        </BaseButton>
        <BaseButton :disabled="!workspaceId" @click="openCreateForm">
          <FilePlus2 class="h-3.5 w-3.5" />
          新建内容资源
        </BaseButton>
      </template>
    </PageTitleBar>

    <div class="grid min-h-0 flex-1 grid-cols-[240px_minmax(0,1fr)] gap-4 overflow-hidden">
      <aside class="flex min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-slate-50/80 shadow-sm">
        <div class="border-b border-slate-200 bg-white p-3">
          <div class="relative">
            <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              v-model="searchKeyword"
              type="text"
              class="h-9 w-full rounded-lg border border-slate-200 bg-slate-50 pl-9 pr-3 text-sm outline-none transition-colors focus:border-indigo-400 focus:bg-white"
              placeholder="搜索资源..."
            />
          </div>
        </div>

        <div class="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
          <section class="rounded-xl border border-slate-200 bg-white p-3">
            <h3 class="mb-2 text-[11px] font-black uppercase tracking-widest text-slate-400">状态</h3>
            <LibrarySegmentedControl
              :model-value="activeView"
              :options="viewTabs"
              :columns="3"
              @update:model-value="handleSelectView"
            />
          </section>

          <section class="rounded-xl border border-slate-200 bg-white p-3">
            <h3 class="mb-2 text-[11px] font-black uppercase tracking-widest text-slate-400">资源类型</h3>
            <div class="grid grid-cols-2 gap-2">
              <button
                v-for="option in assetTypeSegmentOptions"
                :key="option.value || 'all'"
                type="button"
                class="h-8 rounded-lg border px-2 text-xs font-bold transition-colors"
                :class="assetTypeFilter === option.value ? 'border-indigo-200 bg-indigo-50 text-indigo-600 shadow-sm' : 'border-slate-200 bg-slate-50 text-slate-500 hover:border-slate-300 hover:bg-white'"
                @click="handleSelectAssetType(option.value)"
              >
                {{ option.label }}
              </button>
            </div>
          </section>

          <section class="rounded-xl border border-slate-200 bg-white p-3">
            <h3 class="mb-2 text-[11px] font-black uppercase tracking-widest text-slate-400">标签</h3>
            <LibraryChipFilter v-model="activeTagFilter" :options="availableTagOptions" />
          </section>

          <section class="rounded-xl border border-slate-200 bg-white p-3">
            <h3 class="mb-2 text-[11px] font-black uppercase tracking-widest text-slate-400">排序</h3>
            <select
              v-model="sortValue"
              class="h-9 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-semibold text-slate-600 outline-none transition-colors hover:bg-white focus:border-indigo-400 focus:bg-white"
            >
              <option value="updated_at:desc">最近更新</option>
              <option value="created_at:desc">最近创建</option>
              <option value="name:asc">名称升序</option>
              <option value="file_size:desc">文件较大优先</option>
            </select>
          </section>
        </div>
      </aside>

      <main class="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <header class="flex shrink-0 items-center justify-between gap-4 border-b border-slate-100 px-5 py-4">
          <div>
            <h2 class="text-base font-bold text-slate-800">资源预览</h2>
            <p class="mt-1 text-xs text-slate-400">点击资源打开详情弹窗，页面卡片只保留轻量信息。</p>
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <BaseButton
              v-if="activeView === 'active'"
              variant="ghost"
              size="sm"
              :disabled="!hasBatchSelection || batchOperating"
              @click="archiveSelectedAssets"
            >
              <Archive class="h-3.5 w-3.5" />
              批量归档
            </BaseButton>
            <BaseButton
              v-else
              variant="ghost"
              size="sm"
              :disabled="!hasBatchSelection || batchOperating"
              @click="deleteSelectedAssets"
            >
              <Trash2 class="h-3.5 w-3.5" />
              批量删除
            </BaseButton>
            <button
              type="button"
              class="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
              title="刷新资源"
              @click="refreshAssets"
            >
              <RefreshCw class="h-4 w-4" />
            </button>
          </div>
        </header>

        <div v-if="assets.length > 0" class="flex shrink-0 items-center justify-between gap-3 border-b border-slate-100 bg-slate-50/70 px-5 py-2.5">
          <label class="inline-flex items-center gap-2 text-xs font-bold text-slate-600">
            <input
              type="checkbox"
              class="h-4 w-4 rounded border-slate-300 text-indigo-600"
              :checked="allCurrentPageSelected"
              @change="toggleCurrentPageSelection"
            />
            本页全选
          </label>
          <div class="flex min-w-0 items-center gap-3 text-xs font-semibold text-slate-500">
            <span>已选 {{ selectedCount }} 个</span>
            <button
              v-if="hasBatchSelection"
              type="button"
              class="inline-flex h-7 items-center gap-1 rounded-lg px-2 text-slate-500 transition-colors hover:bg-white hover:text-slate-800"
              @click="clearBatchSelection"
            >
              <X class="h-3.5 w-3.5" />
              清空
            </button>
          </div>
        </div>

        <div v-if="loading" class="flex flex-1 flex-col items-center justify-center gap-3">
          <div class="h-8 w-8 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent"></div>
          <span class="text-sm font-bold text-slate-400">正在加载资源...</span>
        </div>

        <div v-else class="min-h-0 flex-1 overflow-y-auto bg-slate-50/60 p-4">
          <div
            v-if="assets.length === 0"
            class="flex h-full min-h-[360px] flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 bg-white text-center"
          >
            <FolderArchive class="mb-3 h-10 w-10 text-slate-300" />
            <p class="text-sm font-semibold text-slate-500">{{ emptyAssetText }}</p>
          </div>

          <div v-else class="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-3">
            <article
              v-for="asset in assets"
              :key="asset.id"
              class="group cursor-pointer overflow-hidden rounded-lg border bg-white transition-all hover:-translate-y-0.5 hover:border-indigo-300 hover:shadow-md"
              :class="resolveAssetCardClass(asset)"
              @click="openAssetDetail(asset)"
            >
              <div class="relative aspect-[16/10] bg-slate-50">
                <label class="absolute left-2 top-2 z-10 inline-flex h-7 w-7 items-center justify-center rounded-md border border-white/80 bg-white/95 shadow-sm" @click.stop>
                  <input
                    type="checkbox"
                    class="h-4 w-4 rounded border-slate-300 text-indigo-600"
                    :checked="isAssetSelected(asset.id)"
                    :aria-label="`选择资源 ${asset.name}`"
                    @change.stop="toggleAssetSelection(asset.id)"
                  />
                </label>
                <img
                  v-if="isImage(asset.original_name) && asset.url"
                  :src="asset.url"
                  class="h-full w-full object-contain"
                  :class="asset.asset_type === 'icon' ? 'p-8' : 'p-2.5'"
                  loading="lazy"
                />
                <PenTool v-else-if="asset.asset_type === 'drawio'" class="absolute left-1/2 top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 text-orange-400" />
                <Workflow v-else-if="asset.asset_type === 'mermaid'" class="absolute left-1/2 top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 text-cyan-500" />
                <BarChart3 v-else-if="asset.asset_type === 'chart'" class="absolute left-1/2 top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 text-emerald-500" />
                <Sigma v-else-if="asset.asset_type === 'formula'" class="absolute left-1/2 top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 text-violet-500" />
                <Video v-else-if="asset.asset_type === 'video'" class="absolute left-1/2 top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 text-rose-500" />
                <FileText v-else class="absolute left-1/2 top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 text-slate-400" />

                <div class="absolute inset-0 flex items-center justify-center gap-2 bg-slate-900/0 opacity-0 transition-all group-hover:bg-slate-900/20 group-hover:opacity-100">
                  <button type="button" class="rounded-full bg-white/95 p-2 text-slate-700 shadow-sm" title="打开详情" @click.stop="openAssetDetail(asset)">
                    <ZoomIn class="h-4 w-4" />
                  </button>
                  <button type="button" class="rounded-full bg-white/95 p-2 text-slate-700 shadow-sm" title="复制资源 name" @click.stop="copyAssetName(asset)">
                    <Copy class="h-4 w-4" />
                  </button>
                </div>
              </div>
              <div class="space-y-1.5 p-2.5">
                <div class="flex items-center justify-between gap-2">
                  <h3 class="truncate text-[13px] font-bold text-slate-800">{{ asset.name }}</h3>
                  <span class="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-black uppercase text-slate-500">{{ asset.asset_type }}</span>
                </div>
                <div class="flex items-center justify-between gap-2 text-[10px] font-bold text-slate-400">
                  <span class="truncate font-mono">{{ asset.original_name }}</span>
                  <span class="shrink-0">{{ resolveAssetStatusBadgeText(asset) }}</span>
                </div>
              </div>
            </article>
          </div>
        </div>

        <PaginationControl
          :page="page"
          :page-size="pageSize"
          :total="total"
          :page-size-options="[12, 24, 48, 96]"
          @update:page="handlePageChange"
          @update:page-size="handlePageSizeChange"
        />
      </main>

    </div>

    <input ref="replaceFileInput" type="file" class="hidden" :accept="activeReplaceAccept" @change="handleReplaceFileChange" />
    <input
      ref="uploadFileInput"
      type="file"
      class="hidden"
      :accept="activeUploadAccept"
      multiple
      @change="handleUploadFileChange"
    />

    <Teleport to="body">
      <Transition name="fade">
        <div v-if="uploadMode" class="fixed inset-0 z-[205] flex items-center justify-center p-4">
          <div class="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" @click="closeUploadForm"></div>
          <div class="relative w-full max-w-xl rounded-2xl bg-white p-6 shadow-xl">
            <div class="flex items-start justify-between gap-3">
              <div>
                <h2 class="text-base font-bold text-slate-800">上传资源</h2>
                <p class="mt-1 text-xs text-slate-400">选择资源类型后上传文件；同名资源会询问是否覆盖。</p>
              </div>
              <BaseCloseButton label="关闭上传资源弹窗" @click="closeUploadForm" />
            </div>
            <div class="mt-5 space-y-4">
              <div>
                <label class="mb-1 block text-xs font-bold text-slate-500">资源类型</label>
                <select v-model="uploadForm.asset_type" class="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-semibold text-slate-700 outline-none focus:border-indigo-400">
                  <option v-for="item in assetTypeOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
                </select>
              </div>
              <div>
                <label class="mb-1 block text-xs font-bold text-slate-500">标签，逗号分隔</label>
                <input v-model="uploadTagsText" class="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm outline-none focus:border-indigo-400" placeholder="可留空" />
              </div>
            </div>
            <footer class="mt-6 flex items-center justify-end gap-3">
              <BaseButton variant="ghost" :disabled="uploading" @click="closeUploadForm">取消</BaseButton>
              <BaseButton :disabled="uploading" @click="triggerUploadSelect">
                <Upload class="h-3.5 w-3.5" />
                {{ uploading ? '上传中...' : '选择文件上传' }}
              </BaseButton>
            </footer>
          </div>
        </div>
      </Transition>

      <Transition name="fade">
        <div v-if="createMode" class="fixed inset-0 z-[210] flex items-center justify-center p-4">
          <div class="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" @click="closeCreateForm"></div>
          <div class="relative flex max-h-[86vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl bg-white shadow-xl">
            <header class="flex shrink-0 items-center justify-between border-b border-slate-100 px-5 py-4">
              <div>
                <h2 class="text-base font-bold text-slate-800">新建内容资源</h2>
                <p class="mt-1 text-xs text-slate-400">支持 SVG 图片、SVG 图标、Draw.io、Mermaid、Chart 和 Formula。</p>
              </div>
              <BaseButton variant="ghost" size="sm" @click="closeCreateForm">取消</BaseButton>
            </header>
            <div class="min-h-0 flex-1 overflow-y-auto p-5">
              <div class="grid gap-3 lg:grid-cols-[160px_minmax(0,1fr)_minmax(0,1fr)]">
                <select v-model="createForm.asset_type" class="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                  <option v-for="item in creatableTypes" :key="item.value" :value="item.value">{{ item.label }}</option>
                </select>
                <input v-model.trim="createForm.name" class="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm" placeholder="资源 name，如 brand_icon" />
                <input v-model.trim="createForm.original_name" class="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm" placeholder="展示文件名，如 brand_icon.svg" />
              </div>
              <textarea
                v-model="createForm.content"
                class="mt-4 h-[420px] w-full rounded-xl border border-slate-200 bg-slate-50 p-4 font-mono text-xs leading-5 text-slate-800 outline-none focus:border-indigo-400"
                placeholder="输入 SVG 图片 / SVG 图标 / Draw.io XML / Mermaid / Chart JSON/YAML / Formula 内容"
              />
            </div>
            <footer class="flex shrink-0 items-center justify-between gap-3 border-t border-slate-100 bg-slate-50 px-5 py-4">
              <p class="text-xs text-slate-500">SVG 会拒绝脚本、事件属性、foreignObject 与远程引用。</p>
              <BaseButton :disabled="saving" @click="createAsset">创建资源</BaseButton>
            </footer>
          </div>
        </div>
      </Transition>

      <Transition name="fade">
        <div v-if="detailAsset" class="fixed inset-0 z-[220] flex p-5">
          <div class="absolute inset-0 bg-slate-950/70 backdrop-blur-sm" @click="closeAssetDetail"></div>
          <div class="relative grid min-h-0 w-full overflow-hidden rounded-2xl bg-white shadow-2xl lg:grid-cols-[minmax(0,1.35fr)_460px]">
            <section class="flex min-h-0 flex-col bg-slate-50">
              <header class="flex shrink-0 items-center justify-between border-b border-slate-200 bg-white px-5 py-4">
                <div class="min-w-0">
                  <h2 class="truncate text-base font-bold text-slate-800">{{ detailAsset.name }}</h2>
                  <p class="mt-1 truncate font-mono text-xs text-slate-400">{{ detailAsset.original_name }}</p>
                </div>
                <BaseCloseButton label="关闭资源详情" @click="closeAssetDetail" />
              </header>
              <div class="min-h-0 flex-1 p-5">
                <AssetPreviewFrame
                  :key="`${detailAsset.id}:${detailAsset.file_hash}`"
                  :workspace-id="workspaceId"
                  :asset="detailAsset"
                />
              </div>
            </section>

            <aside class="flex min-h-0 flex-col border-l border-slate-200 bg-white">
              <div class="shrink-0 border-b border-slate-100 bg-white">
                <div class="px-5 pb-3 pt-4">
                  <div class="grid grid-cols-3 rounded-xl bg-slate-100 p-1">
                    <button
                      v-for="tab in detailTabs"
                      :key="tab.value"
                      type="button"
                      class="h-8 rounded-lg px-3 text-xs font-bold transition-colors"
                      :class="detailTab === tab.value ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-800'"
                      @click="detailTab = tab.value"
                    >
                      {{ tab.label }}
                    </button>
                  </div>
                </div>
                <div class="flex items-center justify-between gap-3 border-t border-slate-100 bg-slate-50/80 px-5 py-3">
                  <span class="shrink-0 text-xs font-black uppercase tracking-widest text-slate-400">资源操作</span>
                  <div class="flex min-w-0 flex-wrap justify-end gap-2">
                    <button
                      type="button"
                      class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-bold text-slate-600 transition-colors hover:border-indigo-200 hover:text-indigo-600"
                      title="替换文件"
                      @click="triggerReplace(detailAsset)"
                    >
                      <Replace class="h-3.5 w-3.5" />
                      替换
                    </button>
                    <button
                      type="button"
                      class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-bold text-slate-600 transition-colors hover:border-indigo-200 hover:text-indigo-600"
                      title="复制资源"
                      @click="copySelected"
                    >
                      <Copy class="h-3.5 w-3.5" />
                      复制
                    </button>
                    <button
                      v-if="detailAsset.status === 'active'"
                      type="button"
                      class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-bold text-slate-600 transition-colors hover:border-amber-200 hover:text-amber-700"
                      title="归档资源"
                      @click="archiveSelected"
                    >
                      <Archive class="h-3.5 w-3.5" />
                      归档
                    </button>
                    <button
                      v-if="detailAsset.status === 'archived' && !detailAsset.history_kind"
                      type="button"
                      class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-bold text-slate-600 transition-colors hover:border-indigo-200 hover:text-indigo-600"
                      title="恢复资源"
                      @click="restoreSelected"
                    >
                      <RotateCcw class="h-3.5 w-3.5" />
                      恢复
                    </button>
                    <button
                      v-if="detailAsset.status === 'archived'"
                      type="button"
                      class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-rose-100 bg-white px-2.5 text-xs font-bold text-rose-600 transition-colors hover:border-rose-200 hover:bg-rose-50"
                      title="删除资源"
                      @click="deleteSelected"
                    >
                      <Trash2 class="h-3.5 w-3.5" />
                      删除
                    </button>
                  </div>
                </div>
              </div>

              <div class="min-h-0 flex-1 overflow-y-auto p-5">
                <div v-if="detailTab === 'basic'" class="space-y-4">
                  <section class="rounded-xl border border-slate-200 bg-slate-50 p-4">
                    <div class="flex items-start justify-between gap-3">
                      <div class="min-w-0">
                        <h3 class="truncate text-sm font-bold text-slate-800">资源摘要</h3>
                        <p class="mt-1 truncate font-mono text-xs text-slate-400">{{ detailAsset.file_hash }}</p>
                      </div>
                      <span class="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-black" :class="detailAsset.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-200 text-slate-600'">
                        {{ resolveAssetStatusBadgeText(detailAsset) }}
                      </span>
                    </div>
                    <dl class="mt-4 grid grid-cols-2 gap-3 text-xs">
                      <div><dt class="text-slate-500">类型</dt><dd class="mt-1 font-bold text-slate-800">{{ detailAsset.asset_type }}</dd></div>
                      <div><dt class="text-slate-500">大小</dt><dd class="mt-1 font-bold text-slate-800">{{ formatBytes(detailAsset.file_size) }}</dd></div>
                      <div><dt class="text-slate-500">Content-Type</dt><dd class="mt-1 truncate font-mono text-slate-700">{{ detailAsset.content_type || '-' }}</dd></div>
                      <div><dt class="text-slate-500">引用数</dt><dd class="mt-1 font-bold text-slate-800">{{ referenceCountText }}</dd></div>
                    </dl>
                  </section>
                  <div>
                    <label class="mb-1 block text-xs font-bold text-slate-500">资源 name</label>
                    <input v-model="editForm.name" class="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm outline-none focus:border-indigo-400 focus:bg-white" />
                  </div>
                  <div>
                    <label class="mb-1 block text-xs font-bold text-slate-500">展示文件名</label>
                    <input v-model="editForm.original_name" class="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm outline-none focus:border-indigo-400 focus:bg-white" />
                  </div>
                  <div>
                    <label class="mb-1 block text-xs font-bold text-slate-500">描述</label>
                    <textarea v-model="editForm.description" rows="4" class="w-full resize-y rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none focus:border-indigo-400 focus:bg-white"></textarea>
                  </div>
                  <div>
                    <label class="mb-1 block text-xs font-bold text-slate-500">标签，逗号分隔</label>
                    <input v-model="editTagsText" class="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm outline-none focus:border-indigo-400 focus:bg-white" />
                  </div>
                </div>

                <div v-else-if="detailTab === 'content'" class="flex min-h-[520px] flex-col">
                  <div v-if="!detailAsset.content_editable" class="flex flex-1 items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50 p-6 text-center">
                    <div>
                      <FileText class="mx-auto mb-3 h-10 w-10 text-slate-300" />
                      <p class="text-sm font-bold text-slate-600">该资源不支持文本内容编辑</p>
                      <p class="mt-2 text-xs leading-6 text-slate-400">位图图标和位图图片只能复制、归档、删除或维护元数据。</p>
                    </div>
                  </div>
                  <template v-else>
                    <textarea v-model="contentDraft" class="min-h-0 flex-1 resize-none rounded-xl border border-slate-200 bg-slate-50 p-4 font-mono text-xs leading-5 text-slate-800 outline-none focus:border-indigo-400" />
                    <p class="mt-3 text-xs text-slate-500">写入内容会自动保留写入前副本。</p>
                  </template>
                </div>

                <div v-else-if="detailTab === 'references'" class="space-y-4">
                  <div class="flex items-center justify-between">
                    <h3 class="text-sm font-bold text-slate-700">引用明细</h3>
                    <button type="button" class="text-xs font-bold text-indigo-600" @click="loadReferences">刷新</button>
                  </div>
                  <div v-if="referencesLoading" class="text-sm text-slate-500">正在检查引用...</div>
                  <div v-else-if="!referenceSummary?.has_references" class="rounded-xl bg-emerald-50 p-4 text-sm font-bold text-emerald-700">未发现引用阻断。</div>
                  <div v-else class="space-y-3">
                    <div class="rounded-xl bg-rose-50 p-4 text-xs leading-6 text-rose-700">
                      页面 {{ referenceSummary.page_count }}，组件 {{ referenceSummary.component_count }}，组件版本 {{ referenceSummary.component_version_count }}，主题 {{ referenceSummary.theme_count }}，字体 {{ referenceSummary.font_count }}。
                    </div>
                    <section v-for="group in referenceGroups" :key="group.kind" class="rounded-xl border border-slate-200 bg-white p-4">
                      <div class="mb-3 flex items-center justify-between">
                        <h4 class="text-sm font-bold text-slate-700">{{ group.label }}</h4>
                        <span class="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-bold text-slate-500">{{ group.items.length }}</span>
                      </div>
                      <div class="space-y-2">
                        <button
                          v-for="item in group.items"
                          :key="`${item.kind}-${item.id}-${item.version_no || ''}`"
                          type="button"
                          class="flex w-full items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-left text-xs transition-colors hover:bg-indigo-50"
                          @click="goToReference(item)"
                        >
                          <span class="min-w-0 truncate font-semibold text-slate-700">{{ formatReferenceName(item) }}</span>
                          <ArrowUpRight v-if="canOpenReference(item)" class="h-3.5 w-3.5 shrink-0 text-slate-400" />
                        </button>
                      </div>
                    </section>
                  </div>
                </div>
              </div>

              <footer class="flex shrink-0 items-center justify-end gap-2 border-t border-slate-100 bg-slate-50 px-5 py-4">
                <BaseButton variant="ghost" size="sm" @click="closeAssetDetail">关闭</BaseButton>
                <BaseButton v-if="detailTab === 'basic'" size="sm" :disabled="saving" @click="saveAssetMetadata">保存信息</BaseButton>
                <BaseButton v-if="detailTab === 'content' && detailAsset.content_editable" size="sm" :disabled="saving || !canSaveContent" @click="saveContent">
                  <Save class="h-3.5 w-3.5" />
                  写入内容
                </BaseButton>
              </footer>
            </aside>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import {
  Archive,
  ArrowUpRight,
  BarChart3,
  Copy,
  FilePlus2,
  FileText,
  FolderArchive,
  PenTool,
  RefreshCw,
  Replace,
  RotateCcw,
  Save,
  Search,
  Sigma,
  Trash2,
  Upload,
  Video,
  Workflow,
  X,
  ZoomIn,
} from '@lucide/vue'

import {
  archiveWorkspaceAsset,
  batchArchiveWorkspaceAssets,
  batchDeleteWorkspaceAssets,
  copyWorkspaceAsset,
  createWorkspaceAssetContent,
  deleteWorkspaceAsset,
  getWorkspaceAssetContent,
  listWorkspaceAssetTags,
  listWorkspaceAssets,
  previewWorkspaceAssetReferences,
  replaceWorkspaceAssetFile,
  restoreWorkspaceAsset,
  updateWorkspaceAsset,
  updateWorkspaceAssetContent,
  uploadWorkspaceAsset,
} from '@/api/assets'
import { getWorkspace } from '@/api/catalog'
import { getErrorCode, getErrorMessage } from '@/api/http'
import PageTitleBar from '@/components/layout/PageTitleBar.vue'
import AssetPreviewFrame from '@/components/project/AssetPreviewFrame.vue'
import { ASSET_UPLOAD_ACCEPT, getAcceptedAssetExtensionText, isAcceptedAssetFile } from '@/components/project/asset-manager'
import type { AgentMutationRefreshEvent } from '@/components/agent/agent-conversation-panel'
import LibraryChipFilter from '@/components/project/LibraryChipFilter.vue'
import LibrarySegmentedControl from '@/components/project/LibrarySegmentedControl.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseCloseButton from '@/components/ui/BaseCloseButton.vue'
import PaginationControl from '@/components/ui/PaginationControl.vue'
import type { AssetBatchOperationResponse, AssetReferenceSummary, AssetResponse, AssetType } from '@/types/api'
import { createConfirm, Message } from '@/utils/message'
import { buildWorkspaceComponentsPath } from '@/utils/workspace-routes'

type AssetView = 'active' | 'archived' | 'history'
type DetailTab = 'basic' | 'content' | 'references'

interface AssetReferenceItem {
  kind: string
  id: number
  component_id?: number
  name?: string
  version_no?: number
}

const route = useRoute()
const router = useRouter()
const activeView = ref<AssetView>('active')
const assetTypeFilter = ref<AssetType | ''>('')
const activeTag = ref<string | null>(null)
const searchKeyword = ref('')
const sortValue = ref('updated_at:desc')
const loading = ref(false)
const saving = ref(false)
const uploading = ref(false)
const batchOperating = ref(false)
const referencesLoading = ref(false)
const createMode = ref(false)
const uploadMode = ref(false)
const assets = ref<AssetResponse[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(24)
const availableTags = ref<string[]>([])
const selectedAsset = ref<AssetResponse | null>(null)
const selectedAssetIds = ref<Set<number>>(new Set())
const detailAsset = ref<AssetResponse | null>(null)
const detailTab = ref<DetailTab>('basic')
const contentDraft = ref('')
const originalContent = ref('')
const referenceSummary = ref<AssetReferenceSummary | null>(null)
const replaceFileInput = ref<HTMLInputElement | null>(null)
const uploadFileInput = ref<HTMLInputElement | null>(null)
const replacingAsset = ref<AssetResponse | null>(null)
const openedQueryAssetId = ref<number | null>(null)
const editForm = reactive({
  name: '',
  original_name: '',
  description: '',
})
const editTagsText = ref('')

const viewTabs = [
  { value: 'active', label: '启用' },
  { value: 'archived', label: '已归档' },
  { value: 'history', label: '历史' },
]
const detailTabs: Array<{ value: DetailTab; label: string }> = [
  { value: 'basic', label: '基础信息' },
  { value: 'content', label: '内容编辑' },
  { value: 'references', label: '引用检查' },
]
const assetTypeOptions: Array<{ value: AssetType; label: string }> = [
  { value: 'icon', label: '图标' },
  { value: 'image', label: '图片' },
  { value: 'video', label: '视频' },
  { value: 'drawio', label: 'Draw.io' },
  { value: 'mermaid', label: 'Mermaid' },
  { value: 'chart', label: 'Chart' },
  { value: 'formula', label: 'Formula' },
]
const assetTypeSegmentOptions: Array<{ value: AssetType | ''; label: string }> = [
  { value: '', label: '全部' },
  ...assetTypeOptions,
]
const creatableTypes = assetTypeOptions.filter(item => ['icon', 'image', 'drawio', 'mermaid', 'chart', 'formula'].includes(item.value))
const createForm = reactive({
  asset_type: 'icon' as AssetType,
  name: '',
  original_name: 'new_icon.svg',
  content: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12 3l8 18H4L12 3z"/></svg>',
})
const uploadForm = reactive({
  asset_type: 'image' as AssetType,
})
const uploadTagsText = ref('')

const workspaceId = computed(() => Number.parseInt(route.params.workspaceId as string, 10))
const workspaceQuery = useQuery(
  computed(() => ({
    queryKey: ['workspace', workspaceId.value],
    queryFn: () => getWorkspace(workspaceId.value),
    enabled: Number.isFinite(workspaceId.value),
  })),
)
const workspaceTitle = computed(() => {
  const workspaceName = workspaceQuery.data.value?.name
  return workspaceName ? `${workspaceName} · 资源库` : '资源库'
})
const sortParts = computed(() => {
  const [sortBy, sortOrder] = sortValue.value.split(':')
  return {
    sortBy: sortBy || 'updated_at',
    sortOrder: sortOrder === 'asc' ? 'asc' as const : 'desc' as const,
  }
})
const activeTagFilter = computed({
  get: () => activeTag.value || '',
  set: value => {
    activeTag.value = value || null
    resetPage()
  },
})
const availableTagOptions = computed(() => availableTags.value.map(tag => ({ label: tag, value: tag })))
const activeUploadAccept = computed(() => ASSET_UPLOAD_ACCEPT[uploadForm.asset_type])
const emptyAssetText = computed(() => {
  if (searchKeyword.value.trim()) return '未找到相关资源'
  if (activeTag.value) return '当前标签下暂无资源'
  if (activeView.value === 'archived') return '暂无归档资源'
  if (activeView.value === 'history') return '暂无写入历史副本'
  return '暂无资源'
})
const canSaveContent = computed(() => (
  Boolean(detailAsset.value?.content_editable)
  && detailAsset.value?.status === 'active'
  && !detailAsset.value?.history_kind
  && contentDraft.value.trim() !== ''
  && contentDraft.value !== originalContent.value
))
const referenceItems = computed<AssetReferenceItem[]>(() => {
  return (referenceSummary.value?.references || []).map(item => ({
    kind: String(item.kind || ''),
    id: Number(item.id),
    component_id: item.component_id == null ? undefined : Number(item.component_id),
    name: item.name == null ? undefined : String(item.name),
    version_no: item.version_no == null ? undefined : Number(item.version_no),
  }))
})
const referenceGroups = computed(() => {
  const labels: Record<string, string> = {
    page: '页面',
    component: '组件草稿',
    component_version: '组件版本',
    theme: '主题',
    font: '字体配置',
  }
  return Object.entries(labels)
    .map(([kind, label]) => ({
      kind,
      label,
      items: referenceItems.value.filter(item => item.kind === kind),
    }))
    .filter(group => group.items.length > 0)
})
const referenceCountText = computed(() => {
  if (referencesLoading.value) return '检查中'
  if (!referenceSummary.value?.has_references) return '0'
  return String(
    referenceSummary.value.page_count
    + referenceSummary.value.component_count
    + referenceSummary.value.component_version_count
    + referenceSummary.value.theme_count
    + referenceSummary.value.font_count,
  )
})
const activeReplaceAccept = computed(() => {
  const assetType = replacingAsset.value?.asset_type || detailAsset.value?.asset_type
  return assetType ? ASSET_UPLOAD_ACCEPT[assetType] : ''
})
const selectedCount = computed(() => selectedAssetIds.value.size)
const hasBatchSelection = computed(() => selectedCount.value > 0)
const currentPageAssetIds = computed(() => assets.value.map(asset => asset.id))
const allCurrentPageSelected = computed(() => (
  currentPageAssetIds.value.length > 0
  && currentPageAssetIds.value.every(assetId => selectedAssetIds.value.has(assetId))
))

watch(
  [workspaceId, activeView, assetTypeFilter, activeTag, searchKeyword, sortValue, page, pageSize],
  () => {
    void refreshAssets()
  },
  { immediate: true },
)

watch([activeView, assetTypeFilter, activeTag, searchKeyword, sortValue, page, pageSize], () => {
  clearBatchSelection()
})

watch([workspaceId, assetTypeFilter], ([id]) => {
  if (Number.isFinite(id)) {
    void loadTags()
  }
}, { immediate: true })

watch(
  () => createForm.asset_type,
  (type) => {
    const next = defaultCreateTemplate(type)
    createForm.original_name = next.originalName
    createForm.content = next.content
  },
)

watch(searchKeyword, resetPage)
watch(sortValue, resetPage)

async function refreshAssets(): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  loading.value = true
  try {
    const status = activeView.value === 'active' ? 'active' : 'archived'
    const includeHistory = activeView.value === 'history'
    const response = await listWorkspaceAssets(workspaceId.value, {
      status,
      includeHistory,
      historyOnly: activeView.value === 'history',
      assetType: assetTypeFilter.value || undefined,
      excludeAssetType: assetTypeFilter.value ? undefined : 'font',
      tag: activeTag.value || undefined,
      keyword: searchKeyword.value.trim() || undefined,
      page: page.value,
      page_size: pageSize.value,
      sort_by: sortParts.value.sortBy,
      sort_order: sortParts.value.sortOrder,
    })
    assets.value = response.items
    total.value = response.total
    pruneBatchSelection()
    syncSelectionAfterListLoad()
    openQueryAssetIfNeeded()
  } catch (error) {
    Message.error(getErrorMessage(error, '读取资源列表失败'))
  } finally {
    loading.value = false
  }
}

async function loadTags(): Promise<void> {
  try {
    const tags = await listWorkspaceAssetTags(workspaceId.value, {
      assetType: assetTypeFilter.value || undefined,
      excludeAssetType: assetTypeFilter.value ? undefined : 'font',
    })
    availableTags.value = tags
    if (activeTag.value && !tags.includes(activeTag.value)) {
      activeTag.value = null
      resetPage()
    }
  } catch {
    availableTags.value = []
    activeTag.value = null
  }
}

function syncSelectionAfterListLoad(): void {
  if (!selectedAsset.value) {
    selectedAsset.value = assets.value[0] ?? null
    referenceSummary.value = null
    return
  }
  const latest = assets.value.find(asset => asset.id === selectedAsset.value?.id) ?? null
  selectedAsset.value = latest ?? assets.value[0] ?? null
  if (detailAsset.value) {
    detailAsset.value = assets.value.find(asset => asset.id === detailAsset.value?.id) ?? detailAsset.value
  }
}

function isAssetSelected(assetId: number): boolean {
  return selectedAssetIds.value.has(assetId)
}

function toggleAssetSelection(assetId: number): void {
  const nextIds = new Set(selectedAssetIds.value)
  if (nextIds.has(assetId)) {
    nextIds.delete(assetId)
  } else {
    nextIds.add(assetId)
  }
  selectedAssetIds.value = nextIds
}

function toggleCurrentPageSelection(): void {
  const nextIds = new Set(selectedAssetIds.value)
  if (allCurrentPageSelected.value) {
    for (const assetId of currentPageAssetIds.value) {
      nextIds.delete(assetId)
    }
  } else {
    for (const assetId of currentPageAssetIds.value) {
      nextIds.add(assetId)
    }
  }
  selectedAssetIds.value = nextIds
}

function clearBatchSelection(): void {
  selectedAssetIds.value = new Set()
}

function pruneBatchSelection(): void {
  const currentIds = new Set(currentPageAssetIds.value)
  selectedAssetIds.value = new Set([...selectedAssetIds.value].filter(assetId => currentIds.has(assetId)))
}

function handleGlobalAgentAssetUpdated(event: Event): void {
  const detail = (event as CustomEvent<AgentMutationRefreshEvent>).detail
  if (!detail) {
    return
  }
  if (detail.workspaceId !== null && detail.workspaceId !== undefined && Number(detail.workspaceId) !== workspaceId.value) {
    return
  }
  const updatedAssetId = Number(detail.assetId)
  void refreshAssets()
  void loadTags()
  if (Number.isFinite(updatedAssetId) && detailAsset.value?.id === updatedAssetId) {
    if (detailTab.value === 'content') {
      void loadContent()
    }
    if (detailTab.value === 'references') {
      void loadReferences()
    }
  }
}

function openQueryAssetIfNeeded(): void {
  const assetId = Number(route.query.assetId)
  if (!Number.isFinite(assetId) || openedQueryAssetId.value === assetId) return
  const matched = assets.value.find(asset => asset.id === assetId)
  if (!matched) return
  openedQueryAssetId.value = assetId
  void openAssetDetail(matched)
}

async function openAssetDetail(asset: AssetResponse): Promise<void> {
  selectedAsset.value = asset
  detailAsset.value = asset
  detailTab.value = 'basic'
  syncEditForm(asset)
  referenceSummary.value = null
  contentDraft.value = ''
  originalContent.value = ''
  await Promise.all([loadContent(), loadReferences()])
}

function closeAssetDetail(): void {
  detailAsset.value = null
}

function syncEditForm(asset: AssetResponse): void {
  editForm.name = asset.name
  editForm.original_name = asset.original_name
  editForm.description = asset.description ?? ''
  editTagsText.value = asset.tags.join(', ')
}

async function loadContent(): Promise<void> {
  const asset = detailAsset.value
  if (!Number.isFinite(workspaceId.value) || !asset?.content_editable) return
  try {
    const result = await getWorkspaceAssetContent(workspaceId.value, asset.id)
    contentDraft.value = result.content
    originalContent.value = result.content
  } catch (error) {
    Message.error(getErrorMessage(error, '读取资源内容失败'))
  }
}

async function loadReferences(): Promise<void> {
  const asset = detailAsset.value || selectedAsset.value
  if (!Number.isFinite(workspaceId.value) || !asset) return
  referencesLoading.value = true
  try {
    referenceSummary.value = await previewWorkspaceAssetReferences(workspaceId.value, asset.id)
  } catch (error) {
    Message.error(getErrorMessage(error, '读取引用关系失败'))
  } finally {
    referencesLoading.value = false
  }
}

function handleSelectView(value: string): void {
  activeView.value = value === 'archived' || value === 'history' ? value : 'active'
  resetPage()
}

function handleSelectAssetType(value: string): void {
  assetTypeFilter.value = assetTypeOptions.some(item => item.value === value) ? value as AssetType : ''
  resetPage()
}

function openUploadForm(): void {
  uploadForm.asset_type = assetTypeFilter.value || 'image'
  uploadTagsText.value = activeTag.value || ''
  uploadMode.value = true
}

function closeUploadForm(): void {
  if (uploading.value) return
  uploadMode.value = false
}

function triggerUploadSelect(): void {
  uploadFileInput.value?.click()
}

async function handleUploadFileChange(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  const files = Array.from(target.files || [])
  if (!Number.isFinite(workspaceId.value) || files.length === 0) {
    target.value = ''
    return
  }

  uploading.value = true
  let successCount = 0
  let firstUploaded: AssetResponse | null = null
  let firstError = ''
  const tags = normalizeTags(uploadTagsText.value)
  try {
    for (const file of files) {
      try {
        const uploaded = await uploadAssetWithOverwriteConfirm(file, tags)
        if (uploaded) {
          successCount += 1
          firstUploaded ||= uploaded
        }
      } catch (error) {
        firstError ||= getErrorMessage(error, '上传资源失败')
      }
    }
    if (successCount > 0) {
      Message.success(files.length === 1 ? '上传成功' : `已上传 ${successCount} 个资源`)
      uploadMode.value = false
      activeView.value = 'active'
      assetTypeFilter.value = uploadForm.asset_type
      page.value = 1
      await Promise.all([refreshAssets(), loadTags()])
      if (firstUploaded) {
        await openAssetDetail(firstUploaded)
      }
    }
    if (firstError) {
      Message.error(successCount > 0 ? `部分资源上传失败：${firstError}` : firstError)
    }
  } finally {
    uploading.value = false
    target.value = ''
  }
}

async function uploadAssetWithOverwriteConfirm(file: File, tags: string[]): Promise<AssetResponse | null> {
  try {
    return await uploadWorkspaceAsset(workspaceId.value, file, uploadForm.asset_type, tags)
  } catch (error) {
    if (getErrorCode(error) !== 'ASSET_NAME_CONFLICT') {
      throw error
    }
    const conflictMessage = getErrorMessage(error, `文件 "${file.name}" 已存在，请确认是否覆盖。`)
    const confirmed = await createConfirm(
      `${conflictMessage} 覆盖后现有页面、路由、主题和预览引用会指向新文件，确认覆盖吗？`,
      '覆盖同名资源',
    )
    if (!confirmed) return null
    return await uploadWorkspaceAsset(workspaceId.value, file, uploadForm.asset_type, tags, undefined, undefined, true)
  }
}

function openCreateForm(): void {
  createMode.value = true
}

function closeCreateForm(): void {
  createMode.value = false
}

async function createAsset(): Promise<void> {
  if (!Number.isFinite(workspaceId.value) || !createForm.name.trim() || !createForm.original_name.trim() || !createForm.content.trim()) {
    Message.warning('请填写资源 name、展示文件名和内容')
    return
  }
  saving.value = true
  try {
    const created = await createWorkspaceAssetContent(workspaceId.value, {
      asset_type: createForm.asset_type,
      name: createForm.name.trim(),
      original_name: createForm.original_name.trim(),
      content: createForm.content,
      tags: [],
    })
    Message.success('资源已创建')
    createMode.value = false
    activeView.value = 'active'
    page.value = 1
    await Promise.all([refreshAssets(), loadTags()])
    await openAssetDetail(created)
  } catch (error) {
    Message.error(getErrorMessage(error, '创建资源失败'))
  } finally {
    saving.value = false
  }
}

async function saveAssetMetadata(): Promise<void> {
  if (!Number.isFinite(workspaceId.value) || !detailAsset.value) return
  if (!editForm.name.trim() || !editForm.original_name.trim()) {
    Message.error('资源 name 和展示文件名不能为空')
    return
  }
  saving.value = true
  try {
    const updated = await updateWorkspaceAsset(
      workspaceId.value,
      detailAsset.value.id,
      editForm.name.trim(),
      editForm.original_name.trim(),
      normalizeTags(editTagsText.value),
      editForm.description.trim() || null,
    )
    Message.success('资源信息已保存')
    detailAsset.value = updated
    selectedAsset.value = updated
    await Promise.all([refreshAssets(), loadTags()])
  } catch (error) {
    Message.error(getErrorMessage(error, '保存资源信息失败'))
  } finally {
    saving.value = false
  }
}

async function saveContent(): Promise<void> {
  if (!Number.isFinite(workspaceId.value) || !detailAsset.value || !canSaveContent.value) return
  saving.value = true
  try {
    const updated = await updateWorkspaceAssetContent(workspaceId.value, detailAsset.value.id, {
      content: contentDraft.value,
      change_note: '资源库页面写入内容',
    })
    Message.success('资源内容已写入，写入前副本已自动归档')
    detailAsset.value = updated
    selectedAsset.value = updated
    originalContent.value = contentDraft.value
    await refreshAssets()
  } catch (error) {
    Message.error(getErrorMessage(error, '写入资源内容失败'))
  } finally {
    saving.value = false
  }
}

async function copySelected(): Promise<void> {
  if (!Number.isFinite(workspaceId.value) || !selectedAsset.value) return
  const defaultName = selectedAsset.value.history_kind
    ? `${selectedAsset.value.original_name.replace(/\W+/g, '_')}_copy`
    : `${selectedAsset.value.name}_copy`
  const name = window.prompt('输入复制后的资源 name', defaultName)
  if (!name?.trim()) return
  try {
    const copied = await copyWorkspaceAsset(workspaceId.value, selectedAsset.value.id, { name: name.trim() })
    Message.success('资源已复制')
    activeView.value = copied.status === 'active' ? 'active' : 'archived'
    page.value = 1
    await refreshAssets()
    await openAssetDetail(copied)
  } catch (error) {
    Message.error(getErrorMessage(error, '复制资源失败'))
  }
}

async function archiveSelected(): Promise<void> {
  const asset = detailAsset.value || selectedAsset.value
  if (!Number.isFinite(workspaceId.value) || !asset) return
  try {
    await archiveWorkspaceAsset(workspaceId.value, asset.id)
    Message.success('资源已归档，现有引用仍可用')
    closeAssetDetail()
    await refreshAssets()
  } catch (error) {
    Message.error(getErrorMessage(error, '归档资源失败'))
  }
}

async function restoreSelected(): Promise<void> {
  const asset = detailAsset.value || selectedAsset.value
  if (!Number.isFinite(workspaceId.value) || !asset) return
  try {
    const restored = await restoreWorkspaceAsset(workspaceId.value, asset.id)
    Message.success('资源已恢复')
    activeView.value = 'active'
    page.value = 1
    await refreshAssets()
    await openAssetDetail(restored)
  } catch (error) {
    Message.error(getErrorMessage(error, '恢复资源失败'))
  }
}

async function deleteSelected(): Promise<void> {
  const asset = detailAsset.value || selectedAsset.value
  if (!Number.isFinite(workspaceId.value) || !asset) return
  await loadReferences()
  if (referenceSummary.value?.has_references) {
    Message.error('资源仍存在引用，不能删除')
    return
  }
  const confirmed = await createConfirm(`确认删除资源「${asset.name}」吗？该操作只允许无引用归档资源。`, '删除资源')
  if (!confirmed) return
  try {
    await deleteWorkspaceAsset(workspaceId.value, asset.id)
    Message.success('资源已删除')
    closeAssetDetail()
    selectedAsset.value = null
    await refreshAssetsWithPageFallback()
  } catch (error) {
    Message.error(getErrorMessage(error, '删除资源失败'))
  }
}

async function archiveSelectedAssets(): Promise<void> {
  const assetIds = [...selectedAssetIds.value]
  if (!Number.isFinite(workspaceId.value) || assetIds.length === 0) return
  const confirmed = await createConfirm(`确认归档选中的 ${assetIds.length} 个资源吗？归档后现有引用仍可用。`, '批量归档资源')
  if (!confirmed) return

  batchOperating.value = true
  try {
    const result = await batchArchiveWorkspaceAssets(workspaceId.value, assetIds)
    showBatchOperationResult(result, '归档')
    closeDetailIfSelected(assetIds)
    clearBatchSelection()
    await refreshAssetsWithPageFallback()
  } catch (error) {
    Message.error(getErrorMessage(error, '批量归档资源失败'))
  } finally {
    batchOperating.value = false
  }
}

async function deleteSelectedAssets(): Promise<void> {
  const assetIds = [...selectedAssetIds.value]
  if (!Number.isFinite(workspaceId.value) || assetIds.length === 0) return
  if (activeView.value === 'active') {
    Message.warning('启用资源需要先归档后才能删除')
    return
  }
  const confirmed = await createConfirm(`确认删除选中的 ${assetIds.length} 个资源吗？该操作只允许无引用的归档或历史资源。`, '批量删除资源')
  if (!confirmed) return

  batchOperating.value = true
  try {
    const result = await batchDeleteWorkspaceAssets(workspaceId.value, assetIds)
    showBatchOperationResult(result, '删除')
    closeDetailIfSelected(assetIds)
    clearBatchSelection()
    await refreshAssetsWithPageFallback()
  } catch (error) {
    Message.error(getErrorMessage(error, '批量删除资源失败'))
  } finally {
    batchOperating.value = false
  }
}

function showBatchOperationResult(result: AssetBatchOperationResponse, actionLabel: string): void {
  if (result.failed_count === 0) {
    Message.success(`已${actionLabel} ${result.succeeded_count} 个资源`)
    return
  }
  if (result.succeeded_count > 0) {
    Message.warning(`已${actionLabel} ${result.succeeded_count} 个资源，${result.failed_count} 个失败：${formatBatchFailure(result)}`)
    return
  }
  Message.error(`批量${actionLabel}失败：${formatBatchFailure(result)}`)
}

function formatBatchFailure(result: AssetBatchOperationResponse): string {
  return result.failures[0]?.detail || '请检查资源状态或引用关系'
}

function closeDetailIfSelected(assetIds: number[]): void {
  if (detailAsset.value && assetIds.includes(detailAsset.value.id)) {
    closeAssetDetail()
  }
  if (selectedAsset.value && assetIds.includes(selectedAsset.value.id)) {
    selectedAsset.value = null
  }
}

function triggerReplace(asset: AssetResponse): void {
  replacingAsset.value = asset
  replaceFileInput.value?.click()
}

async function handleReplaceFileChange(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  const asset = replacingAsset.value
  if (!file || !asset || !Number.isFinite(workspaceId.value)) {
    target.value = ''
    replacingAsset.value = null
    return
  }
  if (!isAcceptedAssetFile(file, asset.asset_type)) {
    Message.warning(`${resolveAssetTypeLabel(asset.asset_type)}资源仅支持 ${getAcceptedAssetExtensionText(asset.asset_type)} 文件。`)
    target.value = ''
    replacingAsset.value = null
    return
  }
  const confirmed = await createConfirm(`确认用 "${file.name}" 替换资源 "${asset.name}" 当前文件吗？`, '替换资源文件')
  if (!confirmed) {
    target.value = ''
    replacingAsset.value = null
    return
  }
  try {
    const updated = await replaceWorkspaceAssetFile(workspaceId.value, asset.id, file)
    Message.success('资源文件已替换')
    detailAsset.value = updated
    selectedAsset.value = updated
    await refreshAssets()
  } catch (error) {
    Message.error(getErrorMessage(error, '替换资源文件失败'))
  } finally {
    target.value = ''
    replacingAsset.value = null
  }
}

async function copyAssetName(asset: AssetResponse): Promise<void> {
  try {
    await navigator.clipboard.writeText(asset.name)
    Message.success('资源 name 已复制到剪贴板。')
  } catch {
    Message.error('复制资源 name 失败，请检查浏览器剪贴板权限。')
  }
}

function resolveAssetCardClass(asset: AssetResponse): string {
  if (isAssetSelected(asset.id)) {
    return 'border-indigo-500 ring-2 ring-indigo-200'
  }
  if (selectedAsset.value?.id === asset.id) {
    return 'border-indigo-400 ring-1 ring-indigo-200'
  }
  return 'border-slate-200'
}

function resolveAssetStatusBadgeText(asset: AssetResponse): string {
  if (asset.history_kind) return '历史副本'
  return asset.status === 'archived' ? '已归档' : '启用'
}

function resolveAssetTypeLabel(assetType: AssetType): string {
  return assetTypeOptions.find(item => item.value === assetType)?.label || assetType
}

function formatReferenceName(item: AssetReferenceItem): string {
  if (item.kind === 'component_version') {
    return `${item.name || '组件'} v${item.version_no || '-'}`
  }
  return item.name || `${item.kind} #${item.id}`
}

function canOpenReference(item: AssetReferenceItem): boolean {
  return item.kind === 'component'
}

function goToReference(item: AssetReferenceItem): void {
  if (!canOpenReference(item)) return
  if (item.kind === 'component') {
    void router.push(buildWorkspaceComponentsPath(workspaceId.value, item.id))
  }
}

function normalizeTags(value: string): string[] {
  return value.split(/[,，]/).map(item => item.trim()).filter(Boolean)
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function isImage(name: string): boolean {
  return /\.(jpeg|jpg|png|gif|webp|svg)$/i.test(name)
}

function handlePageChange(nextPage: number): void {
  page.value = nextPage
}

function handlePageSizeChange(nextPageSize: number): void {
  pageSize.value = nextPageSize
  page.value = 1
}

function resetPage(): void {
  page.value = 1
}

async function refreshAssetsWithPageFallback(): Promise<void> {
  const currentPage = page.value
  await refreshAssets()
  if (assets.value.length === 0 && currentPage > 1) {
    page.value = currentPage - 1
  }
}

function defaultCreateTemplate(type: AssetType): { originalName: string; content: string } {
  if (type === 'image') {
    return {
      originalName: 'image.svg',
      content: [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540">',
        '  <rect width="960" height="540" fill="#f8fafc"/>',
        '  <circle cx="480" cy="270" r="120" fill="#4f46e5" opacity="0.18"/>',
        '  <path d="M260 340C350 210 430 210 520 340s170 130 260 0" fill="none" stroke="#4f46e5" stroke-width="24" stroke-linecap="round"/>',
        '</svg>',
      ].join('\n'),
    }
  }
  if (type === 'drawio') return { originalName: 'diagram.drawio', content: '<mxfile><diagram name="Page-1"><mxGraphModel /></diagram></mxfile>' }
  if (type === 'mermaid') return { originalName: 'flow.mmd', content: 'flowchart TD\n  A[Start] --> B[Done]' }
  if (type === 'chart') return { originalName: 'chart.json', content: '{\n  "title": "示例图表",\n  "series": []\n}' }
  if (type === 'formula') return { originalName: 'formula.tex', content: 'E = mc^2' }
  return { originalName: 'new_icon.svg', content: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12 3l8 18H4L12 3z"/></svg>' }
}

onMounted(() => {
  window.addEventListener('agent:asset-updated', handleGlobalAgentAssetUpdated)
})

onBeforeUnmount(() => {
  window.removeEventListener('agent:asset-updated', handleGlobalAgentAssetUpdated)
})
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>

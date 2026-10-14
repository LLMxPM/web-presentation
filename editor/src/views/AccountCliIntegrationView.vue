<!-- 文件功能：介绍桌面 Agent 与 CLI 接入体系，引导用户创建访问令牌（PAT），并在终端命令指引中支持目标工作空间切换与直达。 -->
<template>
  <div class="account-cli-integration-view space-y-6 pb-16">
    <SettingsPageHeader
      title="桌面 Agent 与 CLI 接入"
      description="连接 Cursor、Claude Desktop 等桌面智能体与本地终端，基于工作空间组件规范和真实 Chromium 渲染直接创作幻灯片。"
    />

    <!-- 核心能力介绍卡片 -->
    <section class="rounded-ui-xl border border-border bg-surface p-6 shadow-xs space-y-4">
      <div class="flex items-start gap-4">
        <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent/10 text-accent">
          <Terminal class="h-6 w-6" />
        </div>
        <div class="space-y-1.5 flex-1 min-w-0">
          <h2 class="text-base font-bold text-text-strong">为什么配合桌面 Agent 创作？</h2>
          <p class="text-sm text-text-secondary leading-relaxed">
            除了在 Web 端直接创作外，官方提供的 <code class="font-mono text-xs bg-surface-muted px-1.5 py-0.5 rounded text-accent">wp</code> 命令行工具配合官方
            <code class="font-mono text-xs bg-surface-muted px-1.5 py-0.5 rounded text-accent">web-presentation</code> Skill，
            支持让本地智能体自主读取工作空间内已发布的组件规范与设计主题，直接编写 Vue SFC 页面源码，并通过异步流水线驱动真实 Chromium 截图进行视觉复核。
          </p>
        </div>
      </div>
    </section>

    <!-- 三步快速起步流程 -->
    <div class="space-y-4">
      <h3 class="text-sm font-bold text-text-muted uppercase tracking-wider px-1">
        快速起步流程
      </h3>

      <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <!-- 步骤 1: 创建令牌 -->
        <div class="rounded-ui-xl border border-border bg-surface p-5 shadow-xs flex flex-col justify-between space-y-4">
          <div class="space-y-2">
            <div class="flex items-center gap-2">
              <span class="flex h-6 w-6 items-center justify-center rounded-full bg-accent text-text-inverse text-xs font-bold">1</span>
              <h4 class="text-sm font-bold text-text-strong">创建访问令牌 (PAT)</h4>
            </div>
            <p class="text-xs text-text-secondary leading-relaxed">
              用于通过 External API 安全访问您的工作空间资源。可授权全部或指定工作空间，并可配置有效期限。
            </p>
          </div>
          <div>
            <UiButton variant="primary" class="w-full" @click="goToCreateToken">
              <template #icon><Key class="h-4 w-4" /></template>
              前往创建访问令牌
            </UiButton>
          </div>
        </div>

        <!-- 步骤 2: 发给智能体 -->
        <div class="rounded-ui-xl border border-border bg-surface p-5 shadow-xs flex flex-col justify-between space-y-4">
          <div class="space-y-2">
            <div class="flex items-center gap-2">
              <span class="flex h-6 w-6 items-center justify-center rounded-full bg-accent text-text-inverse text-xs font-bold">2</span>
              <h4 class="text-sm font-bold text-text-strong">复制提示词给智能体</h4>
            </div>
            <p class="text-xs text-text-secondary leading-relaxed">
              创建令牌成功后，弹窗会为您生成专属提示词。直接粘贴给 Cursor、Claude 等智能体，AI 将自动安装 CLI、登录平台并由 CLI 引导安装技能。
            </p>
          </div>
          <div class="rounded-lg border border-border-muted bg-canvas/70 p-3 text-[11px] text-text-muted flex items-center gap-2">
            <Bot class="h-4 w-4 shrink-0 text-accent" />
            <span>智能体将自动执行环境自检、登录与技能配置</span>
          </div>
        </div>

        <!-- 步骤 3: 唤醒创作 -->
        <div class="rounded-ui-xl border border-border bg-surface p-5 shadow-xs flex flex-col justify-between space-y-4">
          <div class="space-y-2">
            <div class="flex items-center gap-2">
              <span class="flex h-6 w-6 items-center justify-center rounded-full bg-accent text-text-inverse text-xs font-bold">3</span>
              <h4 class="text-sm font-bold text-text-strong">唤醒技能开始创作</h4>
            </div>
            <p class="text-xs text-text-secondary leading-relaxed">
              配置就绪后，在智能体对话中直接对它说：<br />
              <code class="font-mono text-[11px] bg-surface-muted px-1.5 py-0.5 rounded text-accent block mt-1">
                请使用 $web-presentation 完成演示文稿设计
              </code>
            </p>
          </div>
          <div class="rounded-lg border border-border-muted bg-canvas/70 p-3 text-[11px] text-text-muted flex items-center gap-2">
            <Sparkles class="h-4 w-4 shrink-0 text-success" />
            <span>CLI 将交互引导选择技能安装位置</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 极客/终端开发者手动操作指南 -->
    <section class="rounded-ui-xl border border-border bg-surface p-6 shadow-xs space-y-5">
      <div class="flex items-center justify-between gap-3 border-b border-border pb-3">
        <div>
          <h3 class="text-sm font-bold text-text-strong">终端开发者手动指令参考</h3>
          <p class="text-xs text-text-secondary mt-0.5">如果您希望自行在终端手动安装和排查，可以参考以下常用命令：</p>
        </div>
      </div>

      <div class="space-y-4">
        <!-- 1. 安装 CLI -->
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <span class="text-xs font-semibold text-text">1. 安装官方 CLI 工具 (推荐使用 uv)</span>
            <UiButton variant="ghost" size="xs" @click="copyCode(installCommand)">
              <template #icon><Copy class="h-3.5 w-3.5" /></template>
              复制命令
            </UiButton>
          </div>
          <div class="rounded-lg border border-border-muted bg-canvas p-3 font-mono text-xs text-text-secondary flex items-center justify-between">
            <code>{{ installCommand }}</code>
          </div>
        </div>

        <!-- 2. 登录平台 -->
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <span class="text-xs font-semibold text-text">2. 绑定当前平台地址并登录</span>
            <UiButton variant="ghost" size="xs" @click="copyCode(loginCommand)">
              <template #icon><Copy class="h-3.5 w-3.5" /></template>
              复制命令
            </UiButton>
          </div>
          <div class="rounded-lg border border-border-muted bg-canvas p-3 font-mono text-xs text-text-secondary flex items-center justify-between">
            <code>{{ loginCommand }}</code>
          </div>
          <p class="text-[11px] text-text-muted">
            提示：执行后在终端提示时隐藏粘贴您的访问令牌（PAT），避免令牌记录在 shell 历史中。
          </p>
        </div>

        <!-- 3. 安装技能（去掉 --scope project，由 CLI 引导） -->
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <span class="text-xs font-semibold text-text">3. 安装官方智能体技能 (由 CLI 交互引导安装位置)</span>
            <UiButton variant="ghost" size="xs" @click="copyCode('wp skill install')">
              <template #icon><Copy class="h-3.5 w-3.5" /></template>
              复制命令
            </UiButton>
          </div>
          <div class="rounded-lg border border-border-muted bg-canvas p-3 font-mono text-xs text-text-secondary flex items-center justify-between">
            <code>wp skill install</code>
          </div>
          <p class="text-[11px] text-text-muted">
            直接运行 <code class="font-mono text-accent">wp skill install</code>，CLI 将自动提示并引导您选择安装到当前项目（<code class="font-mono text-accent">.agents/skills</code>）还是全局用户目录（<code class="font-mono text-accent">~/.agents/skills</code>）。
          </p>
        </div>

        <!-- 4. 环境自检 -->
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <span class="text-xs font-semibold text-text">4. 连通性与权限诊断</span>
            <UiButton variant="ghost" size="xs" @click="copyCode('wp doctor')">
              <template #icon><Copy class="h-3.5 w-3.5" /></template>
              复制命令
            </UiButton>
          </div>
          <div class="rounded-lg border border-border-muted bg-canvas p-3 font-mono text-xs text-text-secondary flex items-center justify-between">
            <code>wp doctor</code>
          </div>
        </div>

        <!-- 5. 切换激活目标工作空间 -->
        <div class="space-y-3 rounded-lg border border-border-muted bg-canvas/40 p-4" data-testid="cli-workspace-step">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex items-center gap-2 min-w-0">
              <span class="text-xs font-semibold text-text">5. 切换激活目标工作空间</span>
              <UiBadge v-if="currentWorkspace" size="sm" tone="accent">
                ID: {{ currentWorkspace.id }}
              </UiBadge>
            </div>

            <!-- 工作空间切换与直达 -->
            <div class="flex items-center gap-2.5 shrink-0">
              <UiSelect
                v-if="workspaceOptions.length > 0"
                :model-value="selectedWorkspaceId"
                :options="workspaceOptions"
                class="w-56"
                aria-label="切换目标工作空间"
                @update:model-value="handleWorkspaceChange"
              />
              <UiButton
                v-if="currentWorkspace"
                variant="secondary"
                size="sm"
                @click="goToWorkspace(currentWorkspace.id)"
              >
                <template #icon><FolderKanban class="h-4 w-4" /></template>
                进入空间
              </UiButton>
            </div>
          </div>

          <div class="flex items-center justify-between">
            <span class="text-[11px] text-text-muted">
              CLI 连接后执行以下命令激活此工作空间进行幻灯片创作：
            </span>
            <UiButton
              v-if="currentWorkspace"
              variant="ghost"
              size="xs"
              @click="copyCode(`wp workspace use ${currentWorkspace.id}`)"
            >
              <template #icon><Copy class="h-3.5 w-3.5" /></template>
              复制命令
            </UiButton>
          </div>

          <div class="rounded-lg border border-border-muted bg-canvas p-3 font-mono text-xs text-text-secondary flex items-center justify-between">
            <code>wp workspace use {{ currentWorkspace?.id ?? '<ID>' }}</code>
          </div>
        </div>
      </div>
    </section>

    <!-- 开源仓库与生态文档链接 -->
    <section class="rounded-ui-xl border border-border bg-surface p-5 shadow-xs flex flex-wrap items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <ExternalLink class="h-5 w-5 text-text-muted" />
        <div>
          <h4 class="text-sm font-semibold text-text">CLI 官方开源仓库</h4>
          <p class="text-xs text-text-secondary mt-0.5">查看源码、Issue 反馈与最新发版说明。</p>
        </div>
      </div>
      <a
        href="https://github.com/LLMxPM/web-presentation-cli"
        target="_blank"
        rel="noopener noreferrer"
        class="inline-flex items-center gap-1.5 rounded-lg border border-border bg-canvas px-3 py-1.5 text-xs font-semibold text-text hover:bg-surface-hover hover:text-accent transition-colors"
      >
        <span>GitHub: LLMxPM/web-presentation-cli</span>
        <ExternalLink class="h-3.5 w-3.5" />
      </a>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bot, Copy, ExternalLink, FolderKanban, Key, Sparkles, Terminal } from '@lucide/vue'

import SettingsPageHeader from '@/components/layout/SettingsPageHeader.vue'
import { UiBadge, UiButton, UiSelect } from '@/components/ui'
import type { SelectModelValue } from '@/components/ui/select'
import { listWorkspaces } from '@/api/catalog'
import type { WorkspaceItem } from '@/types/api'
import { copyTextToClipboard } from '@/utils/clipboard'
import { resolveCurrentEndpoint } from '@/utils/cli-prompts'

const router = useRouter()
const route = useRoute()
const currentEndpoint = computed(() => resolveCurrentEndpoint())

const installCommand = 'uv tool install web-presentation-cli'
const loginCommand = computed(() => `wp login --endpoint ${currentEndpoint.value}`)

const loadingWorkspaces = ref(false)
const workspaces = ref<WorkspaceItem[]>([])
const selectedWorkspaceId = ref<number | null>(null)

const currentWorkspace = computed(() =>
  workspaces.value.find((w) => w.id === selectedWorkspaceId.value) ?? null
)

const workspaceOptions = computed(() =>
  workspaces.value.map((w) => ({
    label: `${w.name} (ID: ${w.id})`,
    value: w.id,
  }))
)

/**
 * 加载活跃工作空间列表（过滤已归档空间），并根据路由中的 returnTo 参数初始化选中的空间。
 */
async function loadWorkspaces() {
  loadingWorkspaces.value = true
  try {
    const res = await listWorkspaces({ page: 1, page_size: 100, status: 'active' })
    const allItems = res.items || []
    workspaces.value = allItems.filter((w) => w.status !== 'archived')

    const returnTo = String(route.query.returnTo || '')
    const match = returnTo.match(/\/workspaces\/(\d+)/)
    const urlWorkspaceId = match ? Number(match[1]) : null

    if (urlWorkspaceId && workspaces.value.some((w) => w.id === urlWorkspaceId)) {
      selectedWorkspaceId.value = urlWorkspaceId
    } else if (workspaces.value.length > 0) {
      selectedWorkspaceId.value = workspaces.value[0].id
    }
  } catch {
    workspaces.value = []
  } finally {
    loadingWorkspaces.value = false
  }
}

/**
 * 切换工作空间时联动更新 returnTo query。
 * @param val 选择的工作空间 ID
 */
function handleWorkspaceChange(val: SelectModelValue) {
  if (val === null || val === undefined) return
  const wsId = Number(val)
  if (Number.isNaN(wsId)) return
  selectedWorkspaceId.value = wsId
  void router.replace({
    path: route.path,
    query: {
      ...route.query,
      returnTo: `/workspaces/${wsId}/home`,
    },
  })
}

/**
 * 导航直达选中的工作空间首页。
 * @param workspaceId 空间 ID
 */
function goToWorkspace(workspaceId: number) {
  void router.push(`/workspaces/${workspaceId}/home`)
}

/**
 * 跳转至访问令牌页面并自动触发新建弹窗。
 */
function goToCreateToken() {
  void router.push({
    path: '/settings/account/tokens',
    query: {
      action: 'create',
      returnTo: route.query.returnTo,
    },
  })
}

/**
 * 复制指定代码内容到剪贴板。
 * @param text 待复制内容
 */
async function copyCode(text: string) {
  await copyTextToClipboard(text, '命令已复制到剪贴板。')
}

onMounted(() => {
  loadWorkspaces()
})
</script>

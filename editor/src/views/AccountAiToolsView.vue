<!-- 文件功能：个人设置 - 工具配置视图，管理智能体内置工具权限、说明与提示词覆盖，并查看完整只读契约。 -->
<template>
  <div class="account-ai-tools-view space-y-6 pb-16">
    <SettingsPageHeader
      title="工具配置"
      description="管理内容助手内置工具开关、自定义说明覆盖与只读接口契约。"
    >
      <template #actions>
        <div class="flex items-center gap-2">
          <span class="rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-semibold text-text-secondary">
            已启用工具：{{ enabledToolCount }} / {{ allTools.length }}
          </span>
        </div>
      </template>
    </SettingsPageHeader>

    <section class="rounded-ui-xl border border-border bg-surface p-5 shadow-xs space-y-5">
      <!-- 搜索与多维筛选栏 -->
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(240px,1fr)_200px_160px_140px]">
        <SimpleSearchBar v-model="toolKeyword" placeholder="搜索工具名称、Key 或说明" />
        <UiSelect v-model="toolGroupFilter" :options="toolGroupOptions" />
        <UiSelect v-model="toolRiskFilter" :options="toolRiskOptions" />
        <UiSelect v-model="toolEnabledFilter" :options="toolEnabledOptions" />
      </div>

      <!-- 工具数据表格 -->
      <div class="overflow-x-auto rounded-ui-lg border border-border">
        <table class="w-full min-w-[840px] table-fixed text-left text-sm">
          <thead class="bg-canvas text-xs font-semibold text-text-muted">
            <tr>
              <th class="w-[28%] px-4 py-3 whitespace-nowrap">工具名称</th>
              <th class="w-[20%] px-4 py-3 whitespace-nowrap">所属工具组</th>
              <th class="w-28 px-4 py-3 whitespace-nowrap">风险级别</th>
              <th class="w-24 px-4 py-3 whitespace-nowrap">状态</th>
              <th class="px-4 py-3 whitespace-nowrap">说明状态</th>
              <th class="w-24 px-4 py-3 text-right whitespace-nowrap">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border-muted bg-surface">
            <tr
              v-for="tool in filteredTools"
              :key="tool.key"
              class="cursor-pointer transition hover:bg-surface-hover"
              @click="openToolDialog(tool)"
            >
              <td class="px-4 py-3">
                <p class="truncate font-semibold text-text-strong">{{ tool.label }}</p>
                <code class="mt-0.5 block truncate text-[11px] text-text-disabled">{{ tool.key }}</code>
              </td>
              <td class="truncate px-4 py-3 text-text-secondary whitespace-nowrap">{{ tool.group_label }}</td>
              <td class="px-4 py-3 whitespace-nowrap">
                <span class="rounded-full px-2 py-0.5 text-xs font-semibold" :class="riskClass(tool.risk_level)">
                  {{ riskLabel(tool) }}
                </span>
              </td>
              <td class="px-4 py-3 font-semibold whitespace-nowrap" :class="toolDrafts[tool.key]?.enabled ? 'text-success-strong' : 'text-text-disabled'">
                {{ toolDrafts[tool.key]?.enabled ? '启用' : '关闭' }}
              </td>
              <td class="px-4 py-3 text-xs text-text-muted whitespace-nowrap">
                <span>{{ isCustomized(tool) ? '已自定义说明' : '系统默认' }}</span>
                <span v-if="isToolDirty(tool)" class="ml-2 font-semibold text-warning-strong">· 未保存</span>
              </td>
              <td class="px-4 py-3 text-right whitespace-nowrap" @click.stop>
                <UiButton variant="ghost" size="sm" @click="openToolDialog(tool)">配置</UiButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <p v-if="filteredTools.length === 0" class="py-10 text-center text-sm text-text-muted">
        没有符合当前筛选条件的智能体工具。
      </p>
    </section>

    <!-- 工具详情与配置弹窗 -->
    <UiDialog
      :open="toolDialogOpen"
      :title="selectedTool?.label || '工具配置'"
      description="配置当前工具开关与说明覆盖，查看只读契约与调用示例。"
      size="wide"
      @update:open="handleToolDialogVisibility"
    >
      <div v-if="selectedTool" class="space-y-5">
        <!-- 可配置项（开关与提示词覆盖） -->
        <div v-if="selectedTool.configurable && toolDrafts[selectedTool.key]" class="grid gap-4 lg:grid-cols-2">
          <label class="flex items-center gap-3 rounded-ui-lg border border-border bg-canvas px-4 py-3 text-sm font-semibold text-text-strong">
            <UiCheckbox
              :model-value="toolDrafts[selectedTool.key].enabled"
              @update:model-value="toolDrafts[selectedTool.key].enabled = $event === true"
            />
            <span>{{ toolDrafts[selectedTool.key].enabled ? '工具已启用' : '工具已停用' }}</span>
          </label>
          <div class="flex items-center rounded-ui-lg border border-border bg-canvas px-4 py-3 text-xs text-text-muted">
            风险级别：{{ riskLabel(selectedTool) }} · {{ selectedTool.requires_confirmation ? '调用前必须弹窗二次确认' : '自动免确认执行' }}
          </div>
          <UiFormField label="工具说明覆盖" class="lg:col-span-2">
            <UiInput
              :model-value="toolDrafts[selectedTool.key].descriptionOverride"
              type="textarea"
              :rows="3"
              :placeholder="selectedTool.default_description"
              @update:model-value="toolDrafts[selectedTool.key].descriptionOverride = String($event)"
            />
          </UiFormField>
          <UiFormField label="工具指令覆盖 (Instructions)" class="lg:col-span-2">
            <UiInput
              :model-value="toolDrafts[selectedTool.key].instructionsOverride"
              type="textarea"
              :rows="3"
              placeholder="留空表示使用系统默认指令"
              @update:model-value="toolDrafts[selectedTool.key].instructionsOverride = String($event)"
            />
          </UiFormField>
        </div>

        <!-- 只读 Agent 契约展示 -->
        <section class="space-y-4 rounded-ui-lg border border-border bg-canvas p-4">
          <div>
            <h3 class="text-sm font-bold text-text-strong">Agent 契约详情</h3>
            <p class="mt-1 text-xs leading-5 text-text-muted">{{ selectedTool.agent_guide.effective_description }}</p>
          </div>
          <dl class="grid gap-3 text-xs md:grid-cols-2">
            <div class="rounded-ui-md bg-surface p-3 border border-border-muted">
              <dt class="font-semibold text-text-disabled">系统默认说明</dt>
              <dd class="mt-1 leading-5 text-text-strong">{{ selectedTool.agent_guide.system_description }}</dd>
            </div>
            <div class="rounded-ui-md bg-surface p-3 border border-border-muted">
              <dt class="font-semibold text-text-disabled">上下文要求</dt>
              <dd class="mt-1 leading-5 text-text-strong">{{ listText(selectedTool.agent_guide.required_context_fields, '无额外上下文要求') }}</dd>
            </div>
            <div class="rounded-ui-md bg-surface p-3 border border-border-muted">
              <dt class="font-semibold text-text-disabled">运行时披露组</dt>
              <dd class="mt-1 leading-5 text-text-strong">{{ listText(selectedTool.agent_guide.runtime_disclosure_groups, '不通过业务工具组披露') }}</dd>
            </div>
            <div class="rounded-ui-md bg-surface p-3 border border-border-muted">
              <dt class="font-semibold text-text-disabled">内置工具提示词</dt>
              <dd class="mt-1 whitespace-pre-wrap leading-5 text-text-strong">{{ selectedTool.agent_guide.instructions || '无额外内置提示词' }}</dd>
            </div>
          </dl>
          <div class="grid gap-3 xl:grid-cols-2">
            <CodeBlock title="参数 JSON Schema" :value="selectedTool.agent_guide.parameters_schema ?? {}" />
            <CodeBlock title="调用示例" :value="selectedTool.agent_guide.call_example ?? {}" />
            <CodeBlock v-if="selectedTool.agent_guide.response_example !== null && selectedTool.agent_guide.response_example !== undefined" title="返回示例" :value="selectedTool.agent_guide.response_example" />
            <div v-if="selectedTool.agent_guide.response_notes" class="rounded-ui-md border border-border bg-surface p-3 text-xs leading-5 text-text-muted">
              {{ selectedTool.agent_guide.response_notes }}
            </div>
          </div>
        </section>
      </div>

      <template #footer>
        <UiButton
          v-if="selectedTool?.configurable"
          variant="ghost"
          size="sm"
          :loading="savingToolKey === selectedTool.key"
          @click="handleRestoreTool(selectedTool)"
        >
          恢复默认
        </UiButton>
        <UiButton variant="ghost" size="sm" @click="toolDialogOpen = false">关闭</UiButton>
        <UiButton
          v-if="selectedTool?.configurable"
          size="sm"
          :disabled="!isToolDirty(selectedTool)"
          :loading="savingToolKey === selectedTool.key"
          @click="handleSaveTool(selectedTool)"
        >
          保存工具
        </UiButton>
      </template>
    </UiDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { onBeforeRouteLeave } from 'vue-router'

import { listAgentConfigs, updateAgentToolConfig } from '@/api/agent-config'
import { getErrorMessage } from '@/api/http'
import SettingsPageHeader from '@/components/layout/SettingsPageHeader.vue'
import SimpleSearchBar from '@/components/patterns/SimpleSearchBar.vue'
import CodeBlock from '@/components/patterns/CodeBlock.vue'
import { UiButton, UiCheckbox, UiDialog, UiFormField, UiInput, UiSelect } from '@/components/ui'
import type { SelectOption } from '@/components/ui/select'
import type { AgentToolConfigItem } from '@/types/api'
import { Message, createConfirm } from '@/utils/message'

interface ToolDraft {
  enabled: boolean
  descriptionOverride: string
  instructionsOverride: string
}

const queryClient = useQueryClient()

const agentConfigsQuery = useQuery({
  queryKey: ['agent-configs'],
  queryFn: listAgentConfigs,
})

const agentConfig = computed(() => agentConfigsQuery.data.value?.[0] ?? null)
const allTools = computed<AgentToolConfigItem[]>(() => agentConfig.value?.tool_groups.flatMap(group => group.tools) ?? [])

const toolKeyword = ref('')
const toolGroupFilter = ref('all')
const toolRiskFilter = ref('all')
const toolEnabledFilter = ref('all')

const toolDrafts = reactive<Record<string, ToolDraft>>({})
const editingToolKey = ref<string | null>(null)
const toolDialogOpen = ref(false)
const savingToolKey = ref<string | null>(null)

const selectedTool = computed(() => allTools.value.find(tool => tool.key === editingToolKey.value) ?? null)
const enabledToolCount = computed(() => allTools.value.filter(tool => toolDrafts[tool.key]?.enabled).length)

const toolGroupOptions = computed<SelectOption[]>(() => [
  { label: '全部工具组', value: 'all' },
  ...(agentConfig.value?.tool_groups.map(group => ({ label: group.label, value: group.key })) ?? []),
])

const toolRiskOptions: SelectOption[] = [
  { label: '全部风险级别', value: 'all' },
  { label: '只读工具', value: 'read' },
  { label: '写入工具', value: 'write' },
  { label: '危险工具', value: 'danger' },
  { label: '系统工具', value: 'system' },
]

const toolEnabledOptions: SelectOption[] = [
  { label: '全部启用状态', value: 'all' },
  { label: '仅已启用', value: 'enabled' },
  { label: '仅已关闭', value: 'disabled' },
]

const filteredTools = computed(() => {
  const keyword = toolKeyword.value.trim().toLowerCase()
  return allTools.value.filter(tool => {
    const draft = toolDrafts[tool.key]
    const enabled = draft ? draft.enabled : tool.enabled
    const matchesKeyword = !keyword || [tool.label, tool.key, tool.group_label, tool.default_description].some(t => t.toLowerCase().includes(keyword))
    const matchesGroup = toolGroupFilter.value === 'all' || tool.group_key === toolGroupFilter.value
    const matchesRisk = toolRiskFilter.value === 'all' || tool.risk_level === toolRiskFilter.value
    const matchesEnabled = toolEnabledFilter.value === 'all' || (toolEnabledFilter.value === 'enabled' ? enabled : !enabled)
    return matchesKeyword && matchesGroup && matchesRisk && matchesEnabled
  })
})

const anyToolDirty = computed(() => allTools.value.some(tool => isToolDirty(tool)))

watch(
  allTools,
  tools => {
    for (const tool of tools) {
      toolDrafts[tool.key] = {
        enabled: tool.enabled,
        descriptionOverride: tool.description_override ?? '',
        instructionsOverride: tool.instructions_override ?? '',
      }
    }
  },
  { immediate: true },
)

function isCustomized(tool: AgentToolConfigItem): boolean {
  return Boolean(tool.description_override || tool.instructions_override)
}

function isToolDirty(tool: AgentToolConfigItem): boolean {
  const draft = toolDrafts[tool.key]
  if (!draft) return false
  return draft.enabled !== tool.enabled
    || draft.descriptionOverride.trim() !== (tool.description_override ?? '')
    || draft.instructionsOverride.trim() !== (tool.instructions_override ?? '')
}

function riskLabel(tool: AgentToolConfigItem): string {
  if (!tool.configurable) return '系统工具'
  if (tool.requires_confirmation) return '二次确认'
  if (tool.risk_level === 'write') return '写入'
  if (tool.risk_level === 'danger') return '危险'
  return '只读'
}

function riskClass(level: AgentToolConfigItem['risk_level']): string {
  if (level === 'danger') return 'bg-danger-muted text-danger-strong'
  if (level === 'write') return 'bg-warning-muted text-warning-strong'
  if (level === 'system') return 'bg-surface-muted text-text-muted'
  return 'bg-success-muted text-success-strong'
}

function listText(items: string[], emptyText: string): string {
  return items.length ? items.join('、') : emptyText
}

function openToolDialog(tool: AgentToolConfigItem) {
  editingToolKey.value = tool.key
  toolDialogOpen.value = true
}

async function handleToolDialogVisibility(open: boolean) {
  if (open) {
    toolDialogOpen.value = true
    return
  }
  if (selectedTool.value && isToolDirty(selectedTool.value)) {
    const confirmed = await createConfirm('当前工具修改尚未保存，确定关闭并放弃修改吗？', '放弃修改')
    if (!confirmed) return
    // 恢复草稿
    toolDrafts[selectedTool.value.key] = {
      enabled: selectedTool.value.enabled,
      descriptionOverride: selectedTool.value.description_override ?? '',
      instructionsOverride: selectedTool.value.instructions_override ?? '',
    }
  }
  toolDialogOpen.value = false
}

async function handleSaveTool(tool: AgentToolConfigItem) {
  if (!agentConfig.value) return
  const draft = toolDrafts[tool.key]
  if (!draft) return
  try {
    savingToolKey.value = tool.key
    await updateAgentToolConfig(agentConfig.value.id, tool.key, {
      enabled: draft.enabled,
      description_override: draft.descriptionOverride.trim() || null,
      instructions_override: draft.instructionsOverride.trim() || null,
    })
    Message.success(`工具「${tool.label}」配置已保存`)
    await queryClient.invalidateQueries({ queryKey: ['agent-configs'] })
    toolDialogOpen.value = false
  } catch (err) {
    Message.error(getErrorMessage(err, '保存工具失败'))
  } finally {
    savingToolKey.value = null
  }
}

async function handleRestoreTool(tool: AgentToolConfigItem) {
  if (!agentConfig.value) return
  const confirmed = await createConfirm(`确定将工具「${tool.label}」恢复为系统默认配置吗？`, '恢复系统默认')
  if (!confirmed) return
  try {
    savingToolKey.value = tool.key
    await updateAgentToolConfig(agentConfig.value.id, tool.key, {
      enabled: true,
      description_override: null,
      instructions_override: null,
    })
    Message.success(`工具「${tool.label}」已恢复默认`)
    await queryClient.invalidateQueries({ queryKey: ['agent-configs'] })
    toolDrafts[tool.key] = {
      enabled: true,
      descriptionOverride: '',
      instructionsOverride: '',
    }
    toolDialogOpen.value = false
  } catch (err) {
    Message.error(getErrorMessage(err, '恢复工具默认失败'))
  } finally {
    savingToolKey.value = null
  }
}

onBeforeRouteLeave(async () => {
  if (!anyToolDirty.value) return true
  return createConfirm('工具配置有未保存修改，确定离开并丢弃修改吗？', '放弃修改')
})
</script>

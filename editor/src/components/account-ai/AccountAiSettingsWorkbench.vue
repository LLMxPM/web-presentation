<!-- 文件功能：呈现账号 AI 设置的管理后台工作区，组织内容助手配置、模型表格、供应商表格与实体弹窗。 -->
<template>
  <div data-testid="account-ai-settings-admin" class="flex h-full min-h-0 flex-col gap-2">
    <PageHeader class="shrink-0" :icon="Bot" title="AI 设置" description="管理内容助手、模型与供应商连接。" />

    <div class="ai-settings-shell grid min-h-0 flex-1 overflow-hidden rounded-ui-xl border border-border bg-surface shadow-sm">
      <AccountAiSettingsNavigation
        :model-value="section"
        :model-count="models.length"
        :provider-count="providerConfigs.length"
        :assistant-ready="assistantReady"
        @update:model-value="emit('changeSection', $event)"
      />

      <main class="flex min-h-0 min-w-0 flex-col overflow-hidden bg-canvas/60">
        <section v-if="section === 'assistant'" class="flex min-h-0 flex-1 flex-col">
          <header class="shrink-0 border-b border-border-muted bg-surface px-5 py-4">
            <div class="flex min-w-0 items-start justify-between gap-4">
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <h2 class="truncate text-lg font-bold text-text-strong">内容助手</h2>
                  <span class="rounded-full px-2 py-0.5 text-xs font-semibold" :class="assistantReady ? 'bg-success-muted text-success-strong' : 'bg-warning-muted text-warning-strong'">
                    {{ assistantReady ? '已就绪' : '待配置' }}
                  </span>
                </div>
                <p class="mt-1 truncate text-sm text-text-muted">{{ agent?.description || '管理内容模型、视觉能力、提示词和工具权限。' }}</p>
              </div>
              <div class="hidden shrink-0 gap-2 xl:flex">
                <span class="rounded-lg border border-border bg-canvas px-3 py-2 text-xs font-semibold text-text-secondary">内容模型：{{ contentSlot?.llm_config_name || '未绑定' }}</span>
                <span class="rounded-lg border border-border bg-canvas px-3 py-2 text-xs font-semibold text-text-secondary">工具：{{ agent?.enabled_tool_count ?? 0 }}/{{ allTools.length }}</span>
              </div>
            </div>
          </header>

          <UiTabs
            :model-value="assistantTab"
            :items="assistantTabs"
            class="flex min-h-0 flex-1 flex-col bg-surface"
            list-class="shrink-0 px-5"
            content-class="min-h-0 flex-1 overflow-y-auto p-5"
            @update:model-value="emit('changeAssistantTab', $event as AssistantSettingsTab)"
          >
            <template #models>
              <div class="space-y-4">
                <div>
                  <h3 class="text-base font-bold text-text-strong">模型与视觉能力</h3>
                  <p class="mt-1 text-xs text-text-muted">分别绑定内容生成、图片理解与图片生成模型；每一行独立保存。</p>
                </div>
                <div class="overflow-hidden rounded-ui-lg border border-border">
                  <table class="w-full min-w-[760px] table-fixed text-left text-sm">
                    <thead class="bg-canvas text-xs font-semibold text-text-muted">
                      <tr>
                        <th class="w-36 px-4 py-3">能力</th>
                        <th class="px-4 py-3">当前模型</th>
                        <th class="w-28 px-4 py-3">来源</th>
                        <th class="w-24 px-4 py-3">状态</th>
                        <th class="w-[420px] px-4 py-3">配置</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-border-muted bg-surface">
                      <tr v-for="row in slotRows" :key="row.slot">
                        <td class="px-4 py-4 font-semibold text-text-strong">{{ row.label }}</td>
                        <td class="px-4 py-4">
                          <p class="truncate font-semibold text-text">{{ row.binding?.llm_config_name || '未绑定模型' }}</p>
                          <p class="mt-0.5 truncate text-xs text-text-muted">{{ row.binding?.provider_label || '—' }}<span v-if="row.binding?.model_id"> · {{ row.binding.model_id }}</span></p>
                        </td>
                        <td class="px-4 py-4 text-xs font-semibold text-text-secondary">{{ row.binding?.inherited_from_global ? '继承全局' : '个人配置' }}</td>
                        <td class="px-4 py-4">
                          <span class="font-semibold" :class="row.binding?.binding_ready ? 'text-success-strong' : 'text-warning-strong'">{{ row.binding?.binding_ready ? '可用' : '待配置' }}</span>
                        </td>
                        <td class="px-4 py-3">
                          <div class="flex items-center gap-2">
                            <UiCombobox
                              class="min-w-0 flex-1"
                              :model-value="slotDrafts[row.slot] ?? null"
                              :options="row.options"
                              clearable
                              size="compact"
                              placeholder="选择模型"
                              @update:model-value="emit('updateSlotDraft', row.slot, $event === null ? null : Number($event))"
                            />
                            <UiButton size="sm" :loading="bindingSlot === row.slot" @click="emit('saveSlot', row.slot, 'personal')">保存</UiButton>
                            <UiButton v-if="canCreateGlobal && row.slot === contentSlot?.slot" variant="ghost" size="sm" :loading="bindingSlot === `global:${row.slot}`" @click="emit('saveSlot', row.slot, 'global')">设为全局默认</UiButton>
                          </div>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-if="models.length === 0" class="rounded-ui-lg border border-warning-border bg-warning-muted px-4 py-3 text-sm text-warning-strong">
                  还没有可绑定模型，请先前往“模型管理”创建模型。
                  <UiButton class="ml-2" variant="ghost" size="sm" @click="emit('changeSection', 'models')">前往模型管理</UiButton>
                </div>
              </div>
            </template>

            <template #prompt>
              <div class="mx-auto max-w-5xl space-y-4">
                <div class="flex items-start justify-between gap-4">
                  <div>
                    <h3 class="text-base font-bold text-text-strong">助手提示词</h3>
                    <p class="mt-1 text-xs text-text-muted">当前{{ agent?.prompt_customized ? '使用账号自定义提示词' : '使用系统默认提示词' }}。</p>
                  </div>
                  <span v-if="promptDirty" class="rounded-full bg-warning-muted px-2 py-1 text-xs font-semibold text-warning-strong">未保存</span>
                </div>
                <UiFormField label="完整提示词">
                  <UiInput
                    :model-value="promptDraft"
                    type="textarea"
                    :rows="20"
                    placeholder="输入内容助手提示词"
                    @update:model-value="emit('updatePrompt', String($event))"
                  />
                </UiFormField>
                <div class="flex justify-end gap-2 border-t border-border-muted pt-4">
                  <UiButton variant="ghost" :loading="savingPrompt" @click="emit('restorePrompt')">恢复系统默认</UiButton>
                  <UiButton :loading="savingPrompt" :disabled="!promptDirty" @click="emit('savePrompt')">保存提示词</UiButton>
                </div>
              </div>
            </template>

            <template #tools>
              <div class="flex min-h-full flex-col gap-4">
                <div class="grid gap-2 lg:grid-cols-[minmax(240px,1fr)_220px_180px_160px]">
                  <SimpleSearchBar v-model="toolKeyword" placeholder="搜索工具名称、key 或说明" />
                  <UiSelect v-model="toolGroupFilter" :options="toolGroupOptions" />
                  <UiSelect v-model="toolRiskFilter" :options="toolRiskOptions" />
                  <UiSelect v-model="toolEnabledFilter" :options="toolEnabledOptions" />
                </div>
                <div class="overflow-auto rounded-ui-lg border border-border">
                  <table class="w-full min-w-[820px] table-fixed text-left text-sm">
                    <thead class="sticky top-0 z-10 bg-canvas text-xs font-semibold text-text-muted">
                      <tr>
                        <th class="w-[28%] px-4 py-3">工具</th>
                        <th class="w-[20%] px-4 py-3">工具组</th>
                        <th class="w-28 px-4 py-3">风险</th>
                        <th class="w-24 px-4 py-3">状态</th>
                        <th class="px-4 py-3">说明</th>
                        <th class="w-24 px-4 py-3 text-right">操作</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-border-muted bg-surface">
                      <tr v-for="tool in filteredTools" :key="tool.key" class="hover:bg-surface-hover">
                        <td class="px-4 py-3">
                          <p class="truncate font-semibold text-text-strong">{{ tool.label }}</p>
                          <code class="mt-0.5 block truncate text-[11px] text-text-disabled">{{ tool.key }}</code>
                        </td>
                        <td class="truncate px-4 py-3 text-text-secondary">{{ tool.group_label }}</td>
                        <td class="px-4 py-3"><span class="rounded-full px-2 py-1 text-xs font-semibold" :class="riskClass(tool.risk_level)">{{ riskLabel(tool) }}</span></td>
                        <td class="px-4 py-3 font-semibold" :class="toolDrafts[tool.key]?.enabled ? 'text-success-strong' : 'text-text-disabled'">{{ toolDrafts[tool.key]?.enabled ? '启用' : '关闭' }}</td>
                        <td class="px-4 py-3 text-xs text-text-muted">{{ customized(tool) ? '已覆盖' : '系统默认' }}<span v-if="isToolDirty(tool)" class="ml-2 text-warning-strong">· 未保存</span></td>
                        <td class="px-4 py-3 text-right"><UiButton variant="ghost" size="sm" @click="emit('openTool', tool)">配置</UiButton></td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p v-if="filteredTools.length === 0" class="py-10 text-center text-sm text-text-muted">没有符合当前筛选条件的工具。</p>
              </div>
            </template>
          </UiTabs>
        </section>

        <section v-else-if="section === 'models'" class="flex min-h-0 flex-1 flex-col">
          <header class="shrink-0 border-b border-border-muted bg-surface px-5 py-4">
            <div class="flex items-center justify-between gap-4">
              <div><h2 class="text-lg font-bold text-text-strong">模型管理</h2><p class="mt-1 text-xs text-text-muted">管理可供内容助手和视觉能力绑定的模型。</p></div>
              <UiButton @click="emit('createModel')"><Plus class="h-4 w-4" />新建模型</UiButton>
            </div>
            <div class="mt-4 grid gap-2 lg:grid-cols-[minmax(260px,1fr)_180px_220px_160px]">
              <SimpleSearchBar v-model="modelKeyword" placeholder="搜索模型名称、ID 或供应商" />
              <UiSelect v-model="modelTypeFilter" :options="modelTypeOptions" />
              <UiSelect v-model="modelProviderFilter" :options="modelProviderOptions" />
              <UiSelect v-model="modelScopeFilter" :options="scopeOptions" />
            </div>
          </header>
          <div class="min-h-0 flex-1 overflow-hidden">
            <DataState :state="modelDataState" :title="modelDataState === 'empty' ? '没有符合条件的模型' : undefined">
              <AccountAiModelTable class="h-full" :items="filteredModels" @view="emit('viewModel', $event)" @edit="emit('editModel', $event)" @delete="emit('deleteModel', $event)" />
            </DataState>
          </div>
        </section>

        <section v-else class="flex min-h-0 flex-1 flex-col">
          <header class="shrink-0 border-b border-border-muted bg-surface px-5 py-4">
            <div class="flex items-center justify-between gap-4">
              <div><h2 class="text-lg font-bold text-text-strong">供应商管理</h2><p class="mt-1 text-xs text-text-muted">管理独立的 Chat 与图片生成连接凭证。</p></div>
              <UiButton @click="emit('createProvider')"><Plus class="h-4 w-4" />新建供应商</UiButton>
            </div>
            <div class="mt-4 grid gap-2 lg:grid-cols-[minmax(260px,1fr)_180px_160px]">
              <SimpleSearchBar v-model="providerKeyword" placeholder="搜索配置名称、供应商或 key" />
              <UiSelect v-model="providerTypeFilter" :options="providerTypeOptions" />
              <UiSelect v-model="providerScopeFilter" :options="scopeOptions" />
            </div>
          </header>
          <div class="min-h-0 flex-1 overflow-hidden">
            <DataState :state="providerDataState" :title="providerDataState === 'empty' ? '没有符合条件的供应商' : undefined">
              <AccountAiProviderTable class="h-full" :items="filteredProviders" @view="emit('viewProvider', $event)" @edit="emit('editProvider', $event)" @delete="emit('deleteProvider', $event)" />
            </DataState>
          </div>
        </section>
      </main>
    </div>

    <UiDialog :open="providerDialogOpen" title="供应商配置" size="wide" :show-header="false" @update:open="emit('updateProviderDialogOpen', $event)">
      <AccountAiProviderDetail v-bind="providerDetailProps" @cancel="emit('cancelProvider')" @edit="emit('startEditProvider')" @delete-provider="emit('deleteProvider', $event)" @submit="emit('submitProvider')" />
    </UiDialog>

    <UiDialog :open="modelDialogOpen" title="模型配置" size="wide" :show-header="false" @update:open="emit('updateModelDialogOpen', $event)">
      <AccountAiModelDetail
        v-bind="modelDetailProps"
        @cancel="emit('cancelModel')"
        @edit="emit('startEditModel')"
        @delete-model="emit('deleteModel', $event)"
        @format-advanced="emit('formatAdvanced')"
        @submit="emit('submitModel')"
        @update:advanced-config-text="emit('updateAdvancedConfigText', $event)"
        @update:advanced-config-collapsed="emit('updateAdvancedConfigCollapsed', $event)"
      />
    </UiDialog>

    <UiDialog :open="toolDialogOpen" :title="selectedTool?.label || '工具配置'" description="维护当前工具配置并查看面向 Agent 的完整只读契约。" size="wide" @update:open="emit('updateToolDialogOpen', $event)">
      <div v-if="selectedTool" class="space-y-5">
        <div v-if="selectedTool.configurable && toolDrafts[selectedTool.key]" class="grid gap-4 lg:grid-cols-2">
          <label class="flex items-center gap-3 rounded-ui-lg border border-border bg-canvas px-4 py-3 text-sm font-semibold text-text-emphasis">
            <UiCheckbox :model-value="toolDrafts[selectedTool.key].enabled" @update:model-value="emit('updateToolEnabled', selectedTool.key, $event === true)" />
            {{ toolDrafts[selectedTool.key].enabled ? '工具已启用' : '工具已关闭' }}
          </label>
          <div class="rounded-ui-lg border border-border bg-canvas px-4 py-3 text-xs text-text-muted">风险：{{ riskLabel(selectedTool) }} · {{ selectedTool.requires_confirmation ? '需要确认' : '无需额外确认' }}</div>
          <UiFormField label="工具说明覆盖"><UiInput :model-value="toolDrafts[selectedTool.key].descriptionOverride" type="textarea" :rows="5" :placeholder="selectedTool.default_description" @update:model-value="emit('updateToolDescription', selectedTool.key, String($event))" /></UiFormField>
          <UiFormField label="工具提示词覆盖"><UiInput :model-value="toolDrafts[selectedTool.key].instructionsOverride" type="textarea" :rows="5" placeholder="留空表示使用系统默认说明" @update:model-value="emit('updateToolInstructions', selectedTool.key, String($event))" /></UiFormField>
        </div>
        <section class="space-y-4 rounded-ui-lg border border-border bg-canvas p-4">
          <div><h3 class="text-sm font-bold text-text-strong">Agent 完整说明</h3><p class="mt-1 text-xs leading-5 text-text-muted">{{ selectedTool.agent_guide.effective_description }}</p></div>
          <dl class="grid gap-3 text-xs md:grid-cols-2">
            <div class="rounded-ui-md bg-surface p-3"><dt class="font-semibold text-text-disabled">系统默认说明</dt><dd class="mt-1 leading-5 text-text-emphasis">{{ selectedTool.agent_guide.system_description }}</dd></div>
            <div class="rounded-ui-md bg-surface p-3"><dt class="font-semibold text-text-disabled">上下文要求</dt><dd class="mt-1 leading-5 text-text-emphasis">{{ listText(selectedTool.agent_guide.required_context_fields, '无额外上下文') }}</dd></div>
            <div class="rounded-ui-md bg-surface p-3"><dt class="font-semibold text-text-disabled">运行时披露组</dt><dd class="mt-1 leading-5 text-text-emphasis">{{ listText(selectedTool.agent_guide.runtime_disclosure_groups, '不通过业务工具组披露') }}</dd></div>
            <div class="rounded-ui-md bg-surface p-3"><dt class="font-semibold text-text-disabled">工具提示词</dt><dd class="mt-1 whitespace-pre-wrap leading-5 text-text-emphasis">{{ selectedTool.agent_guide.instructions || '无额外工具提示词' }}</dd></div>
          </dl>
          <div class="grid gap-3 xl:grid-cols-2">
            <CodeBlock title="参数 JSON Schema" :value="selectedTool.agent_guide.parameters_schema ?? {}" />
            <CodeBlock title="调用示例" :value="selectedTool.agent_guide.call_example ?? {}" />
            <CodeBlock v-if="selectedTool.agent_guide.response_example !== null && selectedTool.agent_guide.response_example !== undefined" title="返回示例" :value="selectedTool.agent_guide.response_example" />
            <div v-if="selectedTool.agent_guide.response_notes" class="rounded-ui-md border border-border bg-surface p-3 text-xs leading-5 text-text-muted">{{ selectedTool.agent_guide.response_notes }}</div>
          </div>
        </section>
      </div>
      <template #footer>
        <UiButton v-if="selectedTool?.configurable" variant="ghost" :loading="savingToolKey === selectedTool.key" @click="emit('restoreTool', selectedTool)">恢复默认</UiButton>
        <UiButton variant="ghost" @click="emit('updateToolDialogOpen', false)">关闭</UiButton>
        <UiButton v-if="selectedTool?.configurable" :disabled="!isToolDirty(selectedTool)" :loading="savingToolKey === selectedTool.key" @click="emit('saveTool', selectedTool)">保存工具</UiButton>
      </template>
    </UiDialog>
  </div>
</template>

<script setup lang="ts">
import { Bot, Plus } from '@lucide/vue'
import { computed, ref } from 'vue'

import AccountAiModelDetail from './AccountAiModelDetail.vue'
import AccountAiModelTable from './AccountAiModelTable.vue'
import AccountAiProviderDetail from './AccountAiProviderDetail.vue'
import AccountAiProviderTable from './AccountAiProviderTable.vue'
import AccountAiSettingsNavigation from './AccountAiSettingsNavigation.vue'
import CodeBlock from '@/components/patterns/CodeBlock.vue'
import DataState from '@/components/patterns/DataState.vue'
import PageHeader from '@/components/patterns/PageHeader.vue'
import SimpleSearchBar from '@/components/patterns/SimpleSearchBar.vue'
import { UiButton, UiCheckbox, UiCombobox, UiDialog, UiFormField, UiInput, UiSelect, UiTabs } from '@/components/ui'
import type { SelectOption } from '@/components/ui/select'
import type { AgentConfigItem, AgentToolConfigItem, LlmConfigItem, LlmProviderCatalogItem, LlmProviderConfigItem, LlmSlotBindingItem } from '@/types/api'
import type { AiSettingsSection, AssistantSettingsTab, EntityDialogMode } from './account-ai-settings-types'

interface ToolDraft { enabled: boolean; descriptionOverride: string; instructionsOverride: string }
interface ModelForm { scope: 'global' | 'personal'; name: string; provider_config_id: number | null; model_id: string; model_type: 'chat' | 'image_generation'; thinking_enabled: boolean; thinking_effort: string | null; supports_image_input: boolean; context_window_tokens: number }
interface ProviderForm { scope: 'global' | 'personal'; name: string; provider_key: string | null; base_url: string; api_key: string }

const props = defineProps<{
  section: AiSettingsSection; assistantTab: AssistantSettingsTab; agent: AgentConfigItem | null
  models: LlmConfigItem[]; providerConfigs: LlmProviderConfigItem[]; providerCatalog: LlmProviderCatalogItem[]; slots: LlmSlotBindingItem[]
  slotDrafts: Record<string, number | null>; bindingSlot: string | null; promptDraft: string; promptDirty: boolean; savingPrompt: boolean
  toolDrafts: Record<string, ToolDraft>; savingToolKey: string | null; selectedTool: AgentToolConfigItem | null; toolDialogOpen: boolean
  providerDialogOpen: boolean; providerMode: EntityDialogMode; providerForm: ProviderForm; selectedProviderConfigId: number | null; selectedProviderConfig: LlmProviderConfigItem | null; currentProviderForProviderForm: LlmProviderCatalogItem | null; providerOptions: SelectOption[]; savingProviderConfig: boolean; deletingProviderConfigId: number | null; canCreateGlobal: boolean
  modelDialogOpen: boolean; modelMode: EntityDialogMode; modelForm: ModelForm; selectedConfigId: number | null; selectedModel: LlmConfigItem | null; currentProvider: LlmProviderCatalogItem | null; providerConfigOptions: SelectOption[]; advancedConfigText: string; advancedConfigError: string; advancedConfigCollapsed: boolean; savingConfig: boolean; deletingConfigId: number | null
}>()

const emit = defineEmits<{
  changeSection: [value: AiSettingsSection]; changeAssistantTab: [value: AssistantSettingsTab]
  updateSlotDraft: [slot: string, value: number | null]; saveSlot: [slot: string, scope: 'personal' | 'global']
  updatePrompt: [value: string]; savePrompt: []; restorePrompt: []
  openTool: [tool: AgentToolConfigItem]; updateToolDialogOpen: [value: boolean]; updateToolEnabled: [key: string, value: boolean]; updateToolDescription: [key: string, value: string]; updateToolInstructions: [key: string, value: string]; saveTool: [tool: AgentToolConfigItem]; restoreTool: [tool: AgentToolConfigItem]
  createProvider: []; viewProvider: [config: LlmProviderConfigItem]; editProvider: [config: LlmProviderConfigItem]; deleteProvider: [config: LlmProviderConfigItem]; updateProviderDialogOpen: [value: boolean]; cancelProvider: []; startEditProvider: []; submitProvider: []
  createModel: []; viewModel: [config: LlmConfigItem]; editModel: [config: LlmConfigItem]; deleteModel: [config: LlmConfigItem]; updateModelDialogOpen: [value: boolean]; cancelModel: []; startEditModel: []; submitModel: []; formatAdvanced: []; updateAdvancedConfigText: [value: string]; updateAdvancedConfigCollapsed: [value: boolean]
}>()

const assistantTabs = [{ label: '模型与视觉能力', value: 'models' }, { label: '提示词', value: 'prompt' }, { label: '工具配置', value: 'tools' }]
const modelKeyword = ref(''); const modelTypeFilter = ref('all'); const modelProviderFilter = ref('all'); const modelScopeFilter = ref('all')
const providerKeyword = ref(''); const providerTypeFilter = ref('all'); const providerScopeFilter = ref('all')
const toolKeyword = ref(''); const toolGroupFilter = ref('all'); const toolRiskFilter = ref('all'); const toolEnabledFilter = ref('all')
const modelTypeOptions = [{ label: '全部模型类型', value: 'all' }, { label: 'Chat', value: 'chat' }, { label: '图片生成', value: 'image_generation' }]
const providerTypeOptions = [{ label: '全部供应商类型', value: 'all' }, { label: 'Chat', value: 'chat' }, { label: '图片生成', value: 'image_generation' }]
const scopeOptions = [{ label: '全部范围', value: 'all' }, { label: '个人', value: 'personal' }, { label: '全局', value: 'global' }]
const toolRiskOptions = [{ label: '全部风险', value: 'all' }, { label: '系统', value: 'system' }, { label: '只读', value: 'read' }, { label: '写入', value: 'write' }, { label: '危险', value: 'danger' }]
const toolEnabledOptions = [{ label: '全部状态', value: 'all' }, { label: '已启用', value: 'enabled' }, { label: '已关闭', value: 'disabled' }]

/** 汇总当前内容助手绑定状态和工具目录。 */
const contentSlot = computed(() => props.slots.find(slot => slot.slot === props.agent?.llm_slot) ?? null)
const assistantReady = computed(() => Boolean(contentSlot.value?.binding_ready))
const allTools = computed(() => props.agent?.tool_groups.flatMap(group => group.tools) ?? [])
const toolGroupOptions = computed(() => [{ label: '全部工具组', value: 'all' }, ...(props.agent?.tool_groups.map(group => ({ label: group.label, value: group.key })) ?? [])])
const modelProviderOptions = computed(() => [{ label: '全部供应商配置', value: 'all' }, ...props.providerConfigs.map(item => ({ label: item.name, value: String(item.id) }))])

/** 根据管理栏关键字、类型、供应商和范围筛选模型。 */
const filteredModels = computed(() => props.models.filter((item) => {
  const keyword = modelKeyword.value.trim().toLowerCase()
  const searchable = `${item.name} ${item.model_id} ${item.provider_config_name} ${item.provider_label}`.toLowerCase()
  return (!keyword || searchable.includes(keyword))
    && (modelTypeFilter.value === 'all' || (item.model_type ?? 'chat') === modelTypeFilter.value)
    && (modelProviderFilter.value === 'all' || item.provider_config_id === Number(modelProviderFilter.value))
    && (modelScopeFilter.value === 'all' || item.scope === modelScopeFilter.value)
}))

/** 根据管理栏关键字、类型和范围筛选供应商。 */
const filteredProviders = computed(() => props.providerConfigs.filter((item) => {
  const keyword = providerKeyword.value.trim().toLowerCase()
  const searchable = `${item.name} ${item.provider_label} ${item.provider_key}`.toLowerCase()
  return (!keyword || searchable.includes(keyword))
    && (providerTypeFilter.value === 'all' || (item.provider_type ?? 'chat') === providerTypeFilter.value)
    && (providerScopeFilter.value === 'all' || item.scope === providerScopeFilter.value)
}))

/** 根据目录元数据和草稿启用状态筛选助手工具。 */
const filteredTools = computed(() => allTools.value.filter((tool) => {
  const keyword = toolKeyword.value.trim().toLowerCase()
  const enabled = props.toolDrafts[tool.key]?.enabled ?? tool.enabled
  const searchable = `${tool.label} ${tool.key} ${tool.description}`.toLowerCase()
  return (!keyword || searchable.includes(keyword))
    && (toolGroupFilter.value === 'all' || tool.group_key === toolGroupFilter.value)
    && (toolRiskFilter.value === 'all' || tool.risk_level === toolRiskFilter.value)
    && (toolEnabledFilter.value === 'all' || (toolEnabledFilter.value === 'enabled' ? enabled : !enabled))
}))

/** 将筛选结果映射为统一数据状态。 */
const modelDataState = computed(() => props.models.length === 0 ? 'empty' : filteredModels.value.length === 0 ? 'empty' : 'ready')
const providerDataState = computed(() => props.providerConfigs.length === 0 ? 'empty' : filteredProviders.value.length === 0 ? 'empty' : 'ready')

/** 为固定能力槽位生成绑定、可选模型与状态数据。 */
const slotRows = computed(() => {
  const contentSlotKey = props.agent?.llm_slot || 'agent_coordinator'
  return [
    { slot: contentSlotKey, label: '内容生成' },
    { slot: 'image_understanding', label: '图片理解' },
    { slot: 'image_generation', label: '图片生成' },
  ].map(row => ({ ...row, binding: props.slots.find(slot => slot.slot === row.slot) ?? null, options: slotOptions(row.slot) }))
})

/** 按槽位能力约束筛选可绑定模型。 */
function slotOptions(slot: string): SelectOption[] {
  return props.models.filter(item => item.status === 'active').filter(item => slot === 'image_generation' ? item.model_type === 'image_generation' : slot === 'image_understanding' ? (item.model_type ?? 'chat') === 'chat' && item.supports_image_input : (item.model_type ?? 'chat') === 'chat').map(item => ({ label: item.name, value: item.id, description: `${item.provider_config_name} / ${item.model_id}` }))
}

const providerDetailProps = computed(() => ({ form: props.providerForm, selectedProviderConfigId: props.selectedProviderConfigId, selectedProviderConfig: props.selectedProviderConfig, mode: props.providerMode, currentProvider: props.currentProviderForProviderForm, providerOptions: props.providerOptions, savingProviderConfig: props.savingProviderConfig, deletingProviderConfigId: props.deletingProviderConfigId, canCreateGlobal: props.canCreateGlobal }))
const modelDetailProps = computed(() => ({ form: props.modelForm, selectedConfigId: props.selectedConfigId, selectedModel: props.selectedModel, mode: props.modelMode, currentProvider: props.currentProvider, providerConfigOptions: props.providerConfigOptions, advancedConfigText: props.advancedConfigText, advancedConfigError: props.advancedConfigError, advancedConfigCollapsed: props.advancedConfigCollapsed, savingConfig: props.savingConfig, deletingConfigId: props.deletingConfigId, canCreateGlobal: props.canCreateGlobal }))

/** 判断工具是否覆盖了系统默认说明。 */
function customized(tool: AgentToolConfigItem): boolean {
  return Boolean(tool.description_override || tool.instructions_override)
}

/** 比较单个工具当前草稿与服务端配置。 */
function isToolDirty(tool: AgentToolConfigItem): boolean {
  const draft = props.toolDrafts[tool.key]
  return Boolean(draft && (
    draft.enabled !== tool.enabled
    || draft.descriptionOverride.trim() !== (tool.description_override ?? '')
    || draft.instructionsOverride.trim() !== (tool.instructions_override ?? '')
  ))
}

/** 返回工具风险和确认语义的用户文案。 */
function riskLabel(tool: AgentToolConfigItem): string {
  if (!tool.configurable) return '系统工具'
  if (tool.requires_confirmation) return '确认执行'
  if (tool.risk_level === 'write') return '写入工具'
  if (tool.risk_level === 'danger') return '危险工具'
  return '只读工具'
}

/** 返回工具风险标签的视觉样式。 */
function riskClass(level: AgentToolConfigItem['risk_level']): string {
  if (level === 'danger') return 'bg-danger-muted text-danger-strong'
  if (level === 'write') return 'bg-warning-muted text-warning-strong'
  if (level === 'system') return 'bg-surface-muted text-text-muted'
  return 'bg-success-muted text-success-strong'
}

/** 将字符串数组格式化为详情文案。 */
function listText(items: string[], emptyText: string): string {
  return items.length ? items.join('、') : emptyText
}
</script>

<style scoped>
.ai-settings-shell { grid-template-columns: 220px minmax(0, 1fr); }
@media (min-width: 960px) and (max-width: 1179px) { .ai-settings-shell { grid-template-columns: 72px minmax(0, 1fr); } }
@media (max-width: 959px) { .ai-settings-shell { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto minmax(0, 1fr); } }
</style>

<!-- 文件功能：整合账号级 AI 设置，集中管理智能体模型绑定、提示词、工具配置与模型。 -->
<template>
  <div class="space-y-5 pb-10">
    <header class="rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div class="min-w-0">
          <div class="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
            <Bot class="h-4 w-4" />
            <span>账户 AI 设置</span>
          </div>
          <h1 class="mt-2 text-2xl font-bold tracking-tight text-slate-900">AI 设置</h1>

        </div>
        <dl class="grid w-full grid-cols-2 overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 text-center sm:grid-cols-4 lg:w-auto lg:min-w-[560px]">
          <div class="border-b border-r border-slate-200 px-4 py-3 sm:border-b-0">
            <dt class="text-[11px] font-semibold text-slate-400">智能体</dt>
            <dd class="mt-1 text-lg font-bold text-slate-900">{{ agentCount }}</dd>
          </div>
          <div class="border-b border-slate-200 px-4 py-3 sm:border-b-0 sm:border-r">
            <dt class="text-[11px] font-semibold text-slate-400">可用模型</dt>
            <dd class="mt-1 text-lg font-bold text-slate-900">{{ activeModelCount }}</dd>
          </div>
          <div class="border-r border-slate-200 px-4 py-3">
            <dt class="text-[11px] font-semibold text-slate-400">未就绪智能体</dt>
            <dd class="mt-1 text-lg font-bold" :class="unreadySlotCount ? 'text-amber-600' : 'text-emerald-600'">
              {{ unreadySlotCount }}
            </dd>
          </div>
          <div class="px-4 py-3">
            <dt class="text-[11px] font-semibold text-slate-400">工具</dt>
            <dd class="mt-1 text-lg font-bold text-slate-900">{{ allToolCount }}</dd>
          </div>
        </dl>
      </div>
    </header>

    <section class="grid gap-5 xl:grid-cols-[380px_minmax(0,1fr)]">
      <aside class="min-h-[720px] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div class="border-b border-slate-200 p-3">
          <div class="grid grid-cols-3 rounded-xl bg-slate-100 p-1">
            <button
              v-for="tab in sectionTabs"
              :key="tab.key"
              type="button"
              :aria-label="tab.label"
              class="flex min-h-12 min-w-0 flex-col items-center justify-center rounded-lg px-2 py-1 text-xs font-bold transition"
              :class="activeSection === tab.key ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-800'"
              @click="setActiveSection(tab.key)"
            >
              <span class="flex items-center gap-1.5">
                <component :is="tab.icon" class="h-3.5 w-3.5" />
                <span>{{ tab.label }}</span>
              </span>
              <span class="mt-0.5 text-[11px] font-semibold opacity-70">{{ tab.meta }}</span>
            </button>
          </div>
        </div>

        <div v-if="activeSection === 'agents'" class="max-h-[calc(100vh-250px)] overflow-y-auto p-3">
          <div class="mb-3 flex items-center justify-between gap-3">
            <div>
              <p class="text-sm font-semibold text-slate-900">智能体配置</p>
              <p class="mt-0.5 text-xs text-slate-500">{{ agentCount }} 个智能体 · {{ unreadySlotCount }} 个需处理</p>
            </div>
          </div>
          <div v-if="agentConfigsQuery.isFetching.value && !(agentConfigsQuery.data.value?.length)" class="rounded-xl border border-dashed border-slate-200 px-4 py-10 text-center text-sm text-slate-400">
            正在读取智能体配置...
          </div>
          <div v-else-if="agentConfigsQuery.data.value?.length" class="space-y-2">
            <button
              v-for="agent in agentConfigsQuery.data.value"
              :key="agent.id"
              type="button"
              class="w-full rounded-xl border p-3 text-left transition"
              :class="selectedAgentConfig?.id === agent.id ? 'border-indigo-200 bg-indigo-50/70' : 'border-slate-200 bg-white hover:bg-slate-50'"
              @click="selectAgent(agent.id)"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="flex min-w-0 items-start gap-3">
                  <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ring-1" :class="getAgentIconShellClass(agent.icon, selectedAgentConfig?.id === agent.id)">
                    <component :is="resolveAgentIconComponent(agent.icon)" class="h-4 w-4" />
                  </span>
                  <div class="min-w-0">
                    <p class="truncate text-sm font-bold text-slate-900">{{ agent.name }}</p>
                    <p class="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{{ agent.summary }}</p>
                  </div>
                </div>
                <span class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold" :class="getAgentSlotClass(agent)">
                  {{ getAgentSlotLabel(agent) }}
                </span>
              </div>
              <div class="mt-3 grid grid-cols-3 gap-2 text-[11px] font-semibold">
                <span class="rounded-lg bg-slate-100 px-2 py-1 text-slate-500">
                  {{ agent.prompt_customized ? '提示词已改' : '默认提示词' }}
                </span>
                <span class="rounded-lg bg-emerald-50 px-2 py-1 text-emerald-700">
                  {{ agent.enabled_tool_count }} 启用
                </span>
                <span class="rounded-lg bg-amber-50 px-2 py-1 text-amber-700">
                  {{ agent.disabled_tool_count }} 关闭
                </span>
              </div>
            </button>
          </div>
          <div v-else class="rounded-xl border border-dashed border-slate-200 px-4 py-10 text-center text-sm text-slate-400">
            暂无可配置智能体。
          </div>
        </div>

        <div v-else-if="activeSection === 'providers'" class="max-h-[calc(100vh-230px)] overflow-y-auto p-3">
          <div class="mb-3 flex items-center justify-between gap-3">
            <div>
              <p class="text-sm font-semibold text-slate-900">供应商</p>
              <p class="mt-0.5 text-xs text-slate-500">{{ providerCount }} 个配置 · {{ providerMissingKeyCount }} 个缺少密钥</p>
            </div>
            <BaseButton variant="primary" size="sm" @click="resetProviderForm">
              <Plus class="h-3.5 w-3.5" />
              新建供应商
            </BaseButton>
          </div>
          <div v-if="providerConfigsQuery.isFetching.value && !(providerConfigsQuery.data.value?.length)" class="rounded-xl border border-dashed border-slate-200 px-4 py-10 text-center text-sm text-slate-400">
            正在读取供应商...
          </div>
          <div v-else-if="providerConfigsQuery.data.value?.length" class="space-y-2">
            <button
              v-for="config in providerConfigsQuery.data.value"
              :key="config.id"
              type="button"
              class="w-full rounded-xl border p-3 text-left transition"
              :class="selectedProviderConfigId === config.id ? 'border-indigo-200 bg-indigo-50/70' : 'border-slate-200 bg-white hover:bg-slate-50'"
              @click="handleEditProviderConfig(config)"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <p class="truncate text-sm font-bold text-slate-900">{{ config.name }}</p>
                  <p class="mt-1 truncate text-xs text-slate-500">{{ config.provider_label }} · {{ config.base_url || '默认地址' }}</p>
                </div>
                <span class="flex shrink-0 flex-col items-end gap-1">
                  <span
                    class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                    :class="config.scope === 'global' ? 'bg-indigo-50 text-indigo-700' : 'bg-slate-100 text-slate-600'"
                  >
                    {{ config.scope === 'global' ? '全局' : '个人' }}
                  </span>
                  <span
                    class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                    :class="config.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'"
                  >
                    {{ config.status === 'active' ? '启用' : '不可用' }}
                  </span>
                </span>
              </div>
              <div class="mt-3 flex min-w-0 items-center justify-between gap-2">
                <code class="min-w-0 truncate rounded bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-600">{{ config.provider_key }}</code>
                <span class="shrink-0 text-[11px] font-semibold" :class="config.has_api_key ? 'text-slate-500' : 'text-amber-600'">
                  {{ config.has_api_key ? config.api_key_masked : '未保存 API Key' }}
                </span>
              </div>
            </button>
          </div>
          <div v-else class="rounded-xl border border-dashed border-slate-200 px-4 py-10 text-center text-sm text-slate-400">
            还没有供应商。
          </div>
        </div>

        <div v-else class="max-h-[calc(100vh-230px)] overflow-y-auto p-3">
          <div class="mb-3 flex items-center justify-between gap-3">
            <div>
              <p class="text-sm font-semibold text-slate-900">模型</p>
              <p class="mt-0.5 text-xs text-slate-500">{{ modelCount }} 个模型 · {{ activeModelCount }} 个启用</p>
            </div>
            <BaseButton variant="primary" size="sm" @click="resetModelForm">
              <Plus class="h-3.5 w-3.5" />
              新建模型
            </BaseButton>
          </div>
          <div v-if="configsQuery.isFetching.value && !(configsQuery.data.value?.length)" class="rounded-xl border border-dashed border-slate-200 px-4 py-10 text-center text-sm text-slate-400">
            正在读取模型...
          </div>
          <div v-else-if="configsQuery.data.value?.length" class="space-y-2">
            <button
              v-for="config in configsQuery.data.value"
              :key="config.id"
              type="button"
              class="w-full rounded-xl border p-3 text-left transition"
              :class="selectedConfigId === config.id ? 'border-indigo-200 bg-indigo-50/70' : 'border-slate-200 bg-white hover:bg-slate-50'"
              @click="handleEditModel(config)"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <p class="truncate text-sm font-bold text-slate-900">{{ config.name }}</p>
                  <p class="mt-1 truncate text-xs text-slate-500">{{ config.provider_config_name }} / {{ config.model_id }}</p>
                </div>
                <span class="flex shrink-0 flex-col items-end gap-1">
                  <span
                    class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                    :class="config.scope === 'global' ? 'bg-indigo-50 text-indigo-700' : 'bg-slate-100 text-slate-600'"
                  >
                    {{ config.scope === 'global' ? '全局' : '个人' }}
                  </span>
                  <span
                    class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                    :class="config.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'"
                  >
                    {{ config.status === 'active' ? '启用' : '不可用' }}
                  </span>
                </span>
              </div>
              <div class="mt-3 flex min-w-0 items-center justify-between gap-2">
                <code class="min-w-0 truncate rounded bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-600">{{ config.model_id }}</code>
                <span class="shrink-0 text-[11px] font-semibold text-slate-500">
                  {{ config.provider_label }}
                </span>
              </div>
            </button>
          </div>
          <div v-else class="rounded-xl border border-dashed border-slate-200 px-4 py-10 text-center text-sm text-slate-400">
            还没有模型。
          </div>
        </div>
      </aside>

      <main class="min-h-[720px] rounded-2xl border border-slate-200 bg-white shadow-sm">
        <section v-if="activeSection === 'agents' && selectedAgentConfig" class="space-y-5 p-5">
          <div class="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 pb-4">
            <div class="flex min-w-0 items-start gap-3">
              <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ring-1" :class="getAgentIconShellClass(selectedAgentConfig.icon, true)">
                <component :is="resolveAgentIconComponent(selectedAgentConfig.icon)" class="h-5 w-5" />
              </span>
              <div class="min-w-0">
                <h2 class="text-lg font-bold text-slate-900">{{ selectedAgentConfig.name }}</h2>
                <p class="mt-1 max-w-4xl text-sm leading-6 text-slate-500">{{ selectedAgentConfig.description }}</p>
              </div>
            </div>
            <div class="flex flex-wrap justify-end gap-2">
              <span class="rounded-full px-3 py-1 text-xs font-semibold" :class="getAgentSlotClass(selectedAgentConfig)">
                {{ getAgentSlotLabel(selectedAgentConfig) }}
              </span>
              <span class="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-500">
                {{ selectedAgentConfig.enabled_tool_count }} / {{ totalToolCount }} 工具启用
              </span>
            </div>
          </div>

          <nav class="grid gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-2 md:grid-cols-3" aria-label="智能体配置分区">
            <button
              v-for="tab in agentPanelTabs"
              :key="tab.key"
              type="button"
              :aria-label="tab.label"
              class="flex min-h-14 items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-sm transition"
              :class="activeAgentPanel === tab.key ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-600 hover:bg-white/70 hover:text-slate-900'"
              @click="activeAgentPanel = tab.key"
            >
              <span class="min-w-0">
                <span class="block truncate font-bold">{{ tab.label }}</span>
                <span class="mt-0.5 block truncate text-[11px] font-semibold opacity-70">{{ tab.meta }}</span>
              </span>
              <span
                v-if="tab.badge"
                class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold"
                :class="tab.badgeClass"
              >
                {{ tab.badge }}
              </span>
            </button>
          </nav>

          <section v-if="activeAgentPanel === 'binding'" class="space-y-4">
            <article class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div class="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h3 class="text-sm font-bold text-slate-900">模型绑定</h3>
                <p class="mt-1 text-xs leading-5 text-slate-500">
                  绑定项：{{ selectedAgentConfig.llm_slot || '未配置' }}；
                  当前模型：{{ selectedAgentSlot?.llm_config_name || '未绑定可用模型' }}
                  <span v-if="selectedAgentSlot?.inherited_from_global">（继承全局默认）</span>
                </p>
                <p v-if="selectedAgentSlot && !selectedAgentSlot.binding_ready" class="mt-1 text-xs font-semibold text-amber-600">
                  当前智能体未绑定模型，请选择一个启用中的模型。
                </p>
              </div>
              <div class="grid min-w-0 gap-2 sm:grid-cols-[minmax(0,1fr)_auto] 2xl:w-[560px]">
                <SearchableSelect
                  v-if="selectedAgentConfig.llm_slot"
                  v-model="slotDrafts[selectedAgentConfig.llm_slot]"
                  :options="configOptions"
                  clearable
                  size="compact"
                  placeholder="选择模型"
                />
                <div class="flex flex-wrap gap-2 sm:justify-end">
                  <BaseButton
                    variant="primary"
                    size="sm"
                    :disabled="!selectedAgentConfig.llm_slot"
                    :loading="bindingSlot === selectedAgentConfig.llm_slot"
                    @click="handleSaveSelectedAgentSlot()"
                  >
                    保存模型绑定
                  </BaseButton>
                  <BaseButton
                    v-if="canCreateGlobal"
                    variant="ghost"
                    size="sm"
                    :disabled="!selectedAgentConfig.llm_slot"
                    :loading="bindingSlot === `global:${selectedAgentConfig.llm_slot}`"
                    @click="handleSaveSelectedAgentSlot('global')"
                  >
                    设为全局默认
                  </BaseButton>
                </div>
              </div>
            </div>
            </article>
            <div class="grid gap-3 md:grid-cols-3">
              <div class="rounded-xl border border-slate-200 bg-white px-4 py-3">
                <p class="text-[11px] font-semibold text-slate-400">供应商</p>
                <p class="mt-1 truncate text-sm font-bold text-slate-800">{{ selectedAgentSlot?.provider_label || '未配置' }}</p>
              </div>
              <div class="rounded-xl border border-slate-200 bg-white px-4 py-3">
                <p class="text-[11px] font-semibold text-slate-400">模型 ID</p>
                <p class="mt-1 truncate text-sm font-bold text-slate-800">{{ selectedAgentSlot?.model_id || '未配置' }}</p>
              </div>
              <div class="rounded-xl border border-slate-200 bg-white px-4 py-3">
                <p class="text-[11px] font-semibold text-slate-400">图片输入</p>
                <p class="mt-1 text-sm font-bold" :class="selectedAgentSlot?.supports_image_input ? 'text-emerald-700' : 'text-slate-500'">
                  {{ selectedAgentSlot?.supports_image_input ? '可用' : '未启用' }}
                </p>
              </div>
            </div>
          </section>

          <section v-else-if="activeAgentPanel === 'prompts'" class="space-y-3">
            <BaseInput
              v-model="promptDraft"
              type="textarea"
              label="智能体提示词"
              :rows="18"
              placeholder="输入当前账号下的智能体提示词"
            />
            <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
              <p class="text-xs font-semibold" :class="promptDirty ? 'text-amber-600' : 'text-slate-500'">
                {{ promptDirty ? '当前有未保存修改。' : (selectedAgentConfig.prompt_customized ? '当前使用账号自定义提示词。' : '当前使用系统默认提示词。') }}
              </p>
              <div class="flex justify-end gap-2">
                <BaseButton variant="ghost" :loading="savingPrompt" @click="handleRestorePrompt">
                  恢复默认
                </BaseButton>
                <BaseButton variant="primary" :loading="savingPrompt" :disabled="!promptDirty" @click="handleSavePrompt">
                  保存提示词
                </BaseButton>
              </div>
            </div>
          </section>

          <section v-else class="space-y-3">
            <div class="flex items-center justify-between gap-3">
              <div>
                <h3 class="text-sm font-bold text-slate-900">工具配置</h3>
                <p class="mt-1 text-xs text-slate-500">按工具组管理启停、说明覆盖和面向 Agent 的只读工具契约。</p>
              </div>
              <span class="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-500">
                {{ selectedAgentConfig.enabled_tool_count }} / {{ totalToolCount }} 可用
              </span>
            </div>

            <article
              v-for="group in selectedAgentConfig.tool_groups"
              :key="group.key"
              class="overflow-hidden rounded-xl border border-slate-200"
            >
              <button
                type="button"
                class="flex w-full flex-col gap-3 bg-slate-50 px-4 py-3 text-left transition hover:bg-slate-100 md:flex-row md:items-center md:justify-between"
                @click="toggleToolGroup(group.key)"
              >
                <span class="min-w-0">
                  <span class="flex items-center gap-2">
                    <component :is="isToolGroupExpanded(group.key) ? ChevronDown : ChevronRight" class="h-4 w-4 text-slate-400" />
                    <span class="text-sm font-bold text-slate-900">{{ group.label }}</span>
                    <span class="text-xs text-slate-400">{{ getToolGroupEnabledCount(group) }} / {{ group.tools.length }} 启用</span>
                  </span>
                  <span class="ml-6 mt-1 block truncate text-xs text-slate-500">{{ group.description }}</span>
                </span>
              </button>

              <div v-show="isToolGroupExpanded(group.key)" class="space-y-3 border-t border-slate-100 bg-slate-50 p-3">
                <article
                  v-for="tool in group.tools"
                  :key="tool.key"
                  class="rounded-xl border border-slate-200 bg-white p-4"
                >
                  <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div class="min-w-0">
                      <div class="flex flex-wrap items-center gap-2">
                        <p class="text-sm font-bold text-slate-900">{{ tool.label }}</p>
                        <span class="rounded-full px-2 py-0.5 text-[11px] font-semibold" :class="getRiskClass(tool.risk_level)">
                          {{ getRiskLabel(tool) }}
                        </span>
                        <span class="rounded-full px-2 py-0.5 text-[11px] font-semibold" :class="isToolCustomized(tool) ? 'bg-indigo-50 text-indigo-700' : 'bg-slate-100 text-slate-500'">
                          {{ isToolCustomized(tool) ? '已覆盖' : '默认说明' }}
                        </span>
                      </div>
                      <code class="mt-1 block truncate text-[11px] text-slate-400">{{ tool.key }}</code>
                      <p class="mt-2 line-clamp-2 text-xs leading-5 text-slate-500">{{ tool.description }}</p>
                    </div>
                    <div class="flex shrink-0 flex-wrap items-center gap-2 lg:justify-end">
                      <label v-if="tool.configurable && toolDrafts[tool.key]" class="inline-flex h-8 items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs font-semibold">
                        <input
                          v-model="toolDrafts[tool.key].enabled"
                          type="checkbox"
                          class="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                        >
                        <span :class="toolDrafts[tool.key].enabled ? 'text-emerald-700' : 'text-slate-400'">
                          {{ toolDrafts[tool.key].enabled ? '启用' : '关闭' }}
                        </span>
                      </label>
                      <span v-else class="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs font-semibold text-slate-400">
                        <Lock class="h-3.5 w-3.5" />
                        系统只读
                      </span>
                      <BaseButton variant="ghost" size="sm" @click="toggleToolEditor(tool.key)">
                        {{ editingToolKey === tool.key ? '收起' : (tool.configurable ? '编辑' : '说明') }}
                      </BaseButton>
                      <BaseButton
                        v-if="tool.configurable"
                        variant="ghost"
                        size="sm"
                        :loading="savingToolKey === tool.key"
                        :disabled="!isToolDirty(tool)"
                        @click="handleSaveTool(tool)"
                      >
                        保存
                      </BaseButton>
                    </div>
                  </div>

                  <div v-if="editingToolKey === tool.key" class="mt-4 border-t border-slate-100 pt-4">
                    <div v-if="tool.configurable && toolDrafts[tool.key]" class="grid gap-3 lg:grid-cols-2">
                      <BaseInput
                        v-model="toolDrafts[tool.key].descriptionOverride"
                        type="textarea"
                        label="工具说明覆盖"
                        :rows="4"
                        :placeholder="tool.default_description"
                      />
                      <BaseInput
                        v-model="toolDrafts[tool.key].instructionsOverride"
                        type="textarea"
                        label="工具提示词覆盖"
                        :rows="4"
                        placeholder="补充该工具的使用约束；留空表示使用默认说明"
                      />
                    </div>

                    <section class="mt-4 space-y-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
                      <div class="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <h4 class="text-sm font-bold text-slate-900">Agent 完整说明</h4>
                          <p class="mt-1 text-xs leading-5 text-slate-500">{{ tool.agent_guide.effective_description }}</p>
                        </div>
                        <div class="flex flex-wrap gap-2">
                          <code class="rounded bg-white px-2 py-1 text-[11px] font-semibold text-slate-600">{{ tool.agent_guide.tool_name }}</code>
                          <span class="rounded-full px-2 py-1 text-[11px] font-semibold" :class="getRiskClass(tool.agent_guide.risk_level)">
                            {{ getRiskLabel(tool) }}
                          </span>
                        </div>
                      </div>

                      <dl class="grid gap-3 text-xs md:grid-cols-2">
                        <div class="rounded-lg bg-white p-3">
                          <dt class="font-semibold text-slate-400">系统默认说明</dt>
                          <dd class="mt-1 leading-5 text-slate-700">{{ tool.agent_guide.system_description }}</dd>
                        </div>
                        <div class="rounded-lg bg-white p-3">
                          <dt class="font-semibold text-slate-400">上下文要求</dt>
                          <dd class="mt-1 leading-5 text-slate-700">
                            {{ formatGuideList(tool.agent_guide.required_context_fields, '无额外上下文字段') }}
                          </dd>
                        </div>
                        <div class="rounded-lg bg-white p-3">
                          <dt class="font-semibold text-slate-400">运行时披露组</dt>
                          <dd class="mt-1 leading-5 text-slate-700">
                            {{ formatGuideList(tool.agent_guide.runtime_disclosure_groups, '不通过业务工具组披露') }}
                          </dd>
                        </div>
                        <div class="rounded-lg bg-white p-3">
                          <dt class="font-semibold text-slate-400">工具提示词</dt>
                          <dd class="mt-1 whitespace-pre-wrap leading-5 text-slate-700">{{ tool.agent_guide.instructions || '无额外工具提示词' }}</dd>
                        </div>
                      </dl>

                      <div class="grid gap-3 xl:grid-cols-2">
                        <div>
                          <p class="mb-2 text-xs font-semibold text-slate-500">参数 JSON Schema</p>
                          <pre class="max-h-72 overflow-auto rounded-lg bg-slate-950 p-3 text-[11px] leading-5 text-slate-100">{{ formatGuideJson(tool.agent_guide.parameters_schema ?? {}) }}</pre>
                        </div>
                        <div>
                          <p class="mb-2 text-xs font-semibold text-slate-500">调用示例</p>
                          <pre class="max-h-72 overflow-auto rounded-lg bg-slate-950 p-3 text-[11px] leading-5 text-slate-100">{{ formatGuideJson(tool.agent_guide.call_example ?? { tool_name: tool.agent_guide.tool_name, arguments: {} }) }}</pre>
                        </div>
                      </div>

                      <div>
                        <p class="mb-2 text-xs font-semibold text-slate-500">返回示例</p>
                        <pre v-if="hasGuideResponseExample(tool)" class="max-h-72 overflow-auto rounded-lg bg-slate-950 p-3 text-[11px] leading-5 text-slate-100">{{ formatGuideJson(tool.agent_guide.response_example) }}</pre>
                        <p v-else class="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-4 text-xs text-slate-400">暂无返回示例</p>
                        <p v-if="tool.agent_guide.response_notes" class="mt-2 text-xs leading-5 text-slate-500">{{ tool.agent_guide.response_notes }}</p>
                      </div>
                    </section>

                    <div v-if="tool.configurable" class="mt-3 flex justify-end gap-2">
                      <BaseButton variant="ghost" size="sm" :loading="savingToolKey === tool.key" @click="handleRestoreTool(tool)">
                        恢复默认
                      </BaseButton>
                      <BaseButton variant="primary" size="sm" :loading="savingToolKey === tool.key" :disabled="!isToolDirty(tool)" @click="handleSaveTool(tool)">
                        保存工具
                      </BaseButton>
                    </div>
                  </div>
                </article>
              </div>
            </article>
          </section>
        </section>

        <section v-else-if="activeSection === 'agents'" class="flex min-h-[720px] items-center justify-center p-8 text-center text-sm text-slate-400">
          暂无可配置智能体。
        </section>

        <AccountAiProviderDetail
          v-else-if="activeSection === 'providers'"
          :form="providerForm"
          :selected-provider-config-id="selectedProviderConfigId"
          :selected-provider-config="selectedProviderConfig"
          :mode="providerPanelMode"
          :current-provider="currentProviderForProviderForm"
          :provider-options="providerOptions"
          :saving-provider-config="savingProviderConfig"
          :deleting-provider-config-id="deletingProviderConfigId"
          :can-create-global="canCreateGlobal"
          @delete-provider="handleDeleteProviderConfig"
          @cancel="handleCancelProviderEdit"
          @edit="handleStartEditProviderConfig"
          @submit="handleSubmitProviderConfig"
        />

        <AccountAiModelDetail
          v-else
          v-model:advanced-config-text="advancedConfigText"
          v-model:advanced-config-collapsed="advancedConfigCollapsed"
          :form="modelForm"
          :selected-config-id="selectedConfigId"
          :selected-model="selectedModel"
          :mode="modelPanelMode"
          :current-provider="currentProvider"
          :provider-config-options="providerConfigOptions"
          :advanced-config-error="advancedConfigError"
          :saving-config="savingConfig"
          :deleting-config-id="deletingConfigId"
          :can-create-global="canCreateGlobal"
          @delete-model="handleDeleteModel"
          @cancel="handleCancelModelEdit"
          @edit="handleStartEditModel"
          @format-advanced="formatAdvancedConfig"
          @submit="handleSubmitModel"
        />
      </main>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { Bot, ChevronDown, ChevronRight, Cpu, Lock, Plus, Server } from '@lucide/vue'

import {
  createLlmConfig,
  createLlmProviderConfig,
  deleteLlmConfig,
  deleteLlmProviderConfig,
  listLlmConfigs,
  listLlmProviderConfigs,
  listLlmProviders,
  listLlmSlots,
  updateLlmConfig,
  updateLlmProviderConfig,
  updateLlmSlotBinding,
} from '@/api/llm'
import type { LlmConfigUpdatePayload, LlmProviderConfigUpdatePayload } from '@/api/llm'
import {
  listAgentCatalog,
  listAgentConfigs,
  updateAgentConfig,
  updateAgentToolConfig,
} from '@/api/agent-config'
import { getErrorMessage } from '@/api/http'
import AccountAiModelDetail from '@/components/account-ai/AccountAiModelDetail.vue'
import AccountAiProviderDetail from '@/components/account-ai/AccountAiProviderDetail.vue'
import { getAgentIconShellClass, resolveAgentIconComponent } from '@/components/agent/agent-icon'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import SearchableSelect from '@/components/ui/SearchableSelect.vue'
import type { SelectOption } from '@/components/ui/select'
import { useAuthStore } from '@/stores/auth'
import type {
  AiLlmConfigScope,
  AgentConfigItem,
  AgentToolConfigItem,
  AgentToolGroupConfigItem,
  LlmConfigItem,
  LlmProviderCatalogItem,
  LlmProviderConfigItem,
} from '@/types/api'
import { Message, createConfirm } from '@/utils/message'

type ActiveSection = 'agents' | 'providers' | 'models'
type ActiveAgentPanel = 'binding' | 'prompts' | 'tools'
type ConfigPanelMode = 'create' | 'detail' | 'edit'

const DEFAULT_CONTEXT_WINDOW_TOKENS = 128000
const DEFAULT_MAX_OUTPUT_TOKENS = 32000
const DEFAULT_COMPRESSION_TARGET_RATIO = 0.1
const DEFAULT_NEW_MODEL_PROVIDER_KEY = 'deepseek'

interface LlmFormState {
  scope: AiLlmConfigScope
  name: string
  provider_config_id: number | null
  model_id: string
  thinking_enabled: boolean
  thinking_effort: string | null
  supports_image_input: boolean
  context_window_tokens: number
  max_output_tokens: number
  history_token_ratio: number
  compression_target_ratio: number
}

interface LlmProviderFormState {
  scope: AiLlmConfigScope
  name: string
  provider_key: string | null
  base_url: string
  api_key: string
}

interface ToolDraft {
  enabled: boolean
  descriptionOverride: string
  instructionsOverride: string
}

const queryClient = useQueryClient()
const authStore = useAuthStore()
const activeSection = ref<ActiveSection>('agents')
const activeAgentPanel = ref<ActiveAgentPanel>('binding')

const selectedAgentId = ref('')
const promptDraft = ref('')
const savingPrompt = ref(false)
const savingToolKey = ref<string | null>(null)
const editingToolKey = ref<string | null>(null)
const toolDrafts = reactive<Record<string, ToolDraft>>({})
const expandedGroupKeys = reactive<Record<string, boolean>>({})
const slotDrafts = reactive<Record<string, number | null>>({})
const bindingSlot = ref<string | null>(null)

const selectedProviderConfigId = ref<number | null>(null)
const providerPanelMode = ref<ConfigPanelMode>('create')
const providerCreateRequested = ref(false)
const savingProviderConfig = ref(false)
const deletingProviderConfigId = ref<number | null>(null)
const applyingExistingProviderConfig = ref(false)

const selectedConfigId = ref<number | null>(null)
const modelPanelMode = ref<ConfigPanelMode>('create')
const modelCreateRequested = ref(false)
const advancedConfigText = ref('{}')
const advancedConfigError = ref('')
const advancedConfigCollapsed = ref(true)
const savingConfig = ref(false)
const deletingConfigId = ref<number | null>(null)
const applyingExistingModel = ref(false)

const modelForm = reactive<LlmFormState>({
  scope: 'personal',
  name: '',
  provider_config_id: null,
  model_id: '',
  thinking_enabled: false,
  thinking_effort: null,
  supports_image_input: false,
  context_window_tokens: DEFAULT_CONTEXT_WINDOW_TOKENS,
  max_output_tokens: DEFAULT_MAX_OUTPUT_TOKENS,
  history_token_ratio: 0.5,
  compression_target_ratio: DEFAULT_COMPRESSION_TARGET_RATIO,
})

const providerForm = reactive<LlmProviderFormState>({
  scope: 'personal',
  name: '',
  provider_key: null,
  base_url: '',
  api_key: '',
})

const providersQuery = useQuery({
  queryKey: ['llm-providers'],
  queryFn: listLlmProviders,
})

const configsQuery = useQuery({
  queryKey: ['llm-configs'],
  queryFn: listLlmConfigs,
})

const providerConfigsQuery = useQuery({
  queryKey: ['llm-provider-configs'],
  queryFn: listLlmProviderConfigs,
})

const slotsQuery = useQuery({
  queryKey: ['llm-slots'],
  queryFn: listLlmSlots,
})

const catalogQuery = useQuery({
  queryKey: ['agent-catalog'],
  queryFn: listAgentCatalog,
})

const agentConfigsQuery = useQuery({
  queryKey: ['agent-configs'],
  queryFn: listAgentConfigs,
})

const agentCount = computed(() => agentConfigsQuery.data.value?.length ?? catalogQuery.data.value?.length ?? 0)
const modelCount = computed(() => configsQuery.data.value?.length ?? 0)
const providerCount = computed(() => providerConfigsQuery.data.value?.length ?? 0)
const activeModelCount = computed(() => (configsQuery.data.value ?? []).filter(config => config.status === 'active').length)
const providerMissingKeyCount = computed(() => (providerConfigsQuery.data.value ?? []).filter(config => !config.has_api_key).length)
const unreadySlotCount = computed(() => (slotsQuery.data.value ?? []).filter(slot => !slot.binding_ready).length)
const allToolCount = computed(() => (
  (agentConfigsQuery.data.value ?? catalogQuery.data.value ?? [])
    .reduce((total, agent) => total + agent.tool_groups.reduce((groupTotal, group) => groupTotal + group.tools.length, 0), 0)
))
const canCreateGlobal = computed(() => authStore.user?.role === 'platform_admin')

const sectionTabs = computed(() => [
  {
    key: 'agents' as const,
    label: '智能体',
    meta: `${agentCount.value} 个配置`,
    icon: Bot,
  },
  {
    key: 'providers' as const,
    label: '供应商',
    meta: `${providerCount.value} 个配置`,
    icon: Server,
  },
  {
    key: 'models' as const,
    label: '模型',
    meta: `${activeModelCount.value}/${modelCount.value} 启用`,
    icon: Cpu,
  },
])

const selectedAgentConfig = computed<AgentConfigItem | null>(() => (
  agentConfigsQuery.data.value?.find(item => item.id === selectedAgentId.value)
  ?? agentConfigsQuery.data.value?.[0]
  ?? null
))

const selectedModel = computed<LlmConfigItem | null>(() => (
  configsQuery.data.value?.find(item => item.id === selectedConfigId.value) ?? null
))

const selectedProviderConfig = computed<LlmProviderConfigItem | null>(() => (
  providerConfigsQuery.data.value?.find(item => item.id === selectedProviderConfigId.value) ?? null
))

const selectedModelProviderConfig = computed<LlmProviderConfigItem | null>(() => (
  providerConfigsQuery.data.value?.find(item => item.id === modelForm.provider_config_id) ?? null
))

const selectedAgentSlot = computed(() => {
  const slotKey = selectedAgentConfig.value?.llm_slot
  if (!slotKey) {
    return null
  }
  return slotsQuery.data.value?.find(slot => slot.slot === slotKey) ?? null
})

const totalToolCount = computed(() => (
  selectedAgentConfig.value?.tool_groups.reduce((total, group) => total + group.tools.length, 0) ?? 0
))

const promptDirty = computed(() => {
  if (!selectedAgentConfig.value) return false
  return promptDraft.value.trim() !== selectedAgentConfig.value.effective_prompt.trim()
})

const selectedSlotDirty = computed(() => {
  const slot = selectedAgentConfig.value?.llm_slot
  if (!slot) return false
  return (slotDrafts[slot] ?? null) !== (selectedAgentSlot.value?.llm_config_id ?? null)
})

const dirtyToolCount = computed(() => (
  selectedAgentConfig.value?.tool_groups.reduce(
    (total, group) => total + group.tools.filter(tool => isToolDirty(tool)).length,
    0,
  ) ?? 0
))

const agentPanelTabs = computed(() => [
  {
    key: 'binding' as const,
    label: '模型绑定',
    meta: selectedAgentSlot.value?.binding_ready ? '运行入口已就绪' : '需要选择模型',
    badge: selectedSlotDirty.value ? '未保存' : '',
    badgeClass: 'bg-amber-50 text-amber-700',
  },
  {
    key: 'prompts' as const,
    label: '提示词',
    meta: selectedAgentConfig.value?.prompt_customized ? '已覆盖提示词' : '使用默认提示词',
    badge: promptDirty.value ? '未保存' : '',
    badgeClass: 'bg-amber-50 text-amber-700',
  },
  {
    key: 'tools' as const,
    label: '工具配置',
    meta: `${selectedAgentConfig.value?.enabled_tool_count ?? 0}/${totalToolCount.value} 启用`,
    badge: dirtyToolCount.value ? `${dirtyToolCount.value} 处` : '',
    badgeClass: 'bg-amber-50 text-amber-700',
  },
])

const providerOptions = computed<SelectOption[]>(() => (
  providersQuery.data.value?.map(provider => ({
    label: provider.label,
    value: provider.provider_key,
    description: provider.supports_thinking
      ? `支持 thinking · ${provider.thinking_mode}${provider.default_model_id ? ` · ${provider.default_model_id}` : ''}`
      : '不支持 thinking',
    keywords: [provider.provider_key, provider.provider_adapter],
  })) ?? []
))

const currentProvider = computed<LlmProviderCatalogItem | null>(() => (
  providersQuery.data.value?.find(provider => provider.provider_key === selectedModelProviderConfig.value?.provider_key) ?? null
))

const currentProviderForProviderForm = computed<LlmProviderCatalogItem | null>(() => (
  providersQuery.data.value?.find(provider => provider.provider_key === providerForm.provider_key) ?? null
))

const providerConfigOptions = computed<SelectOption[]>(() => (
  (providerConfigsQuery.data.value ?? [])
    .filter(config => config.scope === modelForm.scope)
    .filter(config => config.status === 'active' || config.id === modelForm.provider_config_id)
    .map(config => ({
      label: config.name,
      value: config.id,
      description: `${config.scope === 'global' ? '全局供应商' : '个人供应商'} · ${config.provider_label}${config.status === 'active' ? '' : ' · 不可用'}`,
      keywords: [config.provider_key, config.provider_label, config.base_url ?? ''],
    }))
))

const configOptions = computed<SelectOption[]>(() => (
  (configsQuery.data.value ?? [])
    .filter(config => config.status === 'active')
    .map(config => ({
      label: config.name,
      value: config.id,
      description: `${config.scope === 'global' ? '全局模型' : '个人模型'} · ${config.provider_config_name} / ${config.model_id}`,
      keywords: [config.provider_key, config.model_id, config.provider_label, config.provider_config_name],
    }))
))

watch(
  () => agentConfigsQuery.data.value,
  (items) => {
    if (!items?.length) {
      selectedAgentId.value = ''
      return
    }
    if (!items.some(item => item.id === selectedAgentId.value)) {
      selectedAgentId.value = items[0].id
    }
  },
  { immediate: true },
)

watch(
  selectedAgentConfig,
  (config) => {
    if (!config) return
    promptDraft.value = config.effective_prompt
    editingToolKey.value = null
    activeAgentPanel.value = 'binding'
    resetToolDrafts(config)
    resetGroupExpansion(config)
  },
  { immediate: true },
)

watch(
  () => slotsQuery.data.value,
  (slots) => {
    for (const slot of slots ?? []) {
      slotDrafts[slot.slot] = slot.llm_config_id
    }
  },
  { immediate: true },
)

watch(
  () => providersQuery.data.value,
  (providers) => {
    if (!providerForm.provider_key && providers?.length) {
      const provider = findDefaultNewModelProvider(providers)
      providerForm.provider_key = provider.provider_key
      prefillProviderFormFromProvider(provider)
    }
  },
  { immediate: true },
)

watch(
  () => configsQuery.data.value,
  () => {
    if (activeSection.value === 'models') {
      openDefaultModelDetail()
    }
  },
  { immediate: true },
)

watch(
  () => providerConfigsQuery.data.value,
  () => {
    if (activeSection.value === 'providers') {
      openDefaultProviderDetail()
    }
  },
  { immediate: true },
)

watch(
  () => [providerConfigsQuery.data.value, modelForm.scope] as const,
  () => {
    if (selectedConfigId.value || modelForm.provider_config_id) {
      return
    }
    const option = providerConfigOptions.value.find(item => !item.disabled)
    const providerConfig = typeof option?.value === 'number'
      ? providerConfigsQuery.data.value?.find(item => item.id === option.value) ?? null
      : null
    modelForm.provider_config_id = providerConfig?.id ?? null
    prefillModelFormFromProvider(findProviderForConfig(providerConfig))
  },
  { immediate: true },
)

watch(
  () => modelForm.scope,
  (scope, previousScope) => {
    if (selectedConfigId.value || scope === previousScope) {
      return
    }
    const providerConfig = findDefaultProviderConfigForScope(scope)
    modelForm.provider_config_id = providerConfig?.id ?? null
    prefillModelFormFromProvider(findProviderForConfig(providerConfig))
  },
)

watch(
  () => providerForm.provider_key,
  (providerKey, previousProviderKey) => {
    const provider = providersQuery.data.value?.find(item => item.provider_key === providerKey) ?? null
    if (!provider || applyingExistingProviderConfig.value) {
      return
    }
    if (providerKey !== previousProviderKey && (!providerForm.base_url || providerForm.base_url === findProviderDefaultBaseUrl(previousProviderKey))) {
      providerForm.base_url = provider.supports_base_url ? provider.default_base_url ?? '' : ''
    }
    if (!provider.supports_api_key) {
      providerForm.api_key = ''
    }
  },
)

watch(
  () => modelForm.provider_config_id,
  (providerConfigId, previousProviderConfigId) => {
    const providerConfig = providerConfigsQuery.data.value?.find(item => item.id === providerConfigId) ?? null
    const previousProviderConfig = providerConfigsQuery.data.value?.find(item => item.id === previousProviderConfigId) ?? null
    const provider = providersQuery.data.value?.find(item => item.provider_key === providerConfig?.provider_key) ?? null
    const previousProviderKey = previousProviderConfig?.provider_key
    if (!provider || applyingExistingModel.value) {
      return
    }
    if (providerConfigId !== previousProviderConfigId && (!modelForm.model_id || modelForm.model_id === findProviderDefaultModelId(previousProviderKey))) {
      modelForm.model_id = provider.default_model_id ?? ''
    }
    if (!provider.supports_thinking) {
      modelForm.thinking_enabled = false
      modelForm.thinking_effort = null
    } else {
      if (
        providerConfigId !== previousProviderConfigId
        && modelForm.thinking_enabled === findProviderDefaultThinkingEnabled(previousProviderKey)
      ) {
        modelForm.thinking_enabled = provider.default_thinking_enabled
      }
      if (!modelForm.thinking_effort || modelForm.thinking_effort === findProviderDefaultThinkingEffort(previousProviderKey)) {
        modelForm.thinking_effort = provider.default_thinking_effort ?? null
      }
    }
    if (
      providerConfigId !== previousProviderConfigId
      && modelForm.supports_image_input === findProviderDefaultSupportsImageInput(previousProviderKey)
    ) {
      modelForm.supports_image_input = provider.default_supports_image_input
    }
    if (
      providerConfigId !== previousProviderConfigId
      && shouldReplaceTokenDefault(modelForm.context_window_tokens, previousProviderKey, 'context')
    ) {
      modelForm.context_window_tokens = provider.default_context_window_tokens ?? DEFAULT_CONTEXT_WINDOW_TOKENS
    }
    if (
      providerConfigId !== previousProviderConfigId
      && shouldReplaceTokenDefault(modelForm.max_output_tokens, previousProviderKey, 'output')
    ) {
      modelForm.max_output_tokens = provider.default_max_output_tokens ?? DEFAULT_MAX_OUTPUT_TOKENS
    }
    if (advancedConfigText.value.trim() === '{}' && Object.keys(provider.advanced_json_hint ?? {}).length > 0) {
      advancedConfigText.value = JSON.stringify(provider.advanced_json_hint, null, 2)
    }
  },
)

/** 选择新建模型的默认供应商；DeepSeek 不可用时回退到目录首项。 */
function findDefaultNewModelProvider(providers: LlmProviderCatalogItem[]) {
  return providers.find(provider => provider.provider_key === DEFAULT_NEW_MODEL_PROVIDER_KEY) ?? providers[0]
}

/** 使用供应商目录默认值预填新建表单，不影响已有模型装载。 */
function prefillModelFormFromProvider(provider: LlmProviderCatalogItem | null) {
  modelForm.model_id = provider?.default_model_id ?? ''
  modelForm.thinking_enabled = Boolean(provider?.supports_thinking && provider.default_thinking_enabled)
  modelForm.thinking_effort = provider?.supports_thinking ? provider.default_thinking_effort ?? null : null
  modelForm.supports_image_input = Boolean(provider?.default_supports_image_input)
  modelForm.context_window_tokens = provider?.default_context_window_tokens ?? DEFAULT_CONTEXT_WINDOW_TOKENS
  modelForm.max_output_tokens = provider?.default_max_output_tokens ?? DEFAULT_MAX_OUTPUT_TOKENS
}

/** 使用供应商目录默认值预填供应商配置表单。 */
function prefillProviderFormFromProvider(provider: LlmProviderCatalogItem | null) {
  providerForm.base_url = provider?.supports_base_url ? provider.default_base_url ?? '' : ''
  if (!provider?.supports_api_key) {
    providerForm.api_key = ''
  }
}

/** 切换账号 AI 设置的一级分区，保留各分区当前表单草稿。 */
function setActiveSection(section: ActiveSection) {
  activeSection.value = section
  if (section === 'providers') {
    openDefaultProviderDetail()
  }
  if (section === 'models') {
    openDefaultModelDetail()
  }
}

/** 进入供应商分区时优先展示已有供应商详情，避免把新建表单作为默认落点。 */
function openDefaultProviderDetail() {
  if (selectedProviderConfigId.value || providerCreateRequested.value) {
    return
  }
  const firstProviderConfig = providerConfigsQuery.data.value?.[0]
  if (!firstProviderConfig) {
    return
  }
  void handleEditProviderConfig(firstProviderConfig)
}

/** 进入模型分区时优先展示已有模型详情，避免把新建表单作为默认落点。 */
function openDefaultModelDetail() {
  if (selectedConfigId.value || modelCreateRequested.value) {
    return
  }
  const firstModel = configsQuery.data.value?.[0]
  if (!firstModel) {
    return
  }
  void handleEditModel(firstModel)
}

/** 选中左侧智能体卡片并切换到智能体详情。 */
function selectAgent(agentId: string) {
  selectedAgentId.value = agentId
  activeSection.value = 'agents'
}

/** 从供应商列表中查找默认 Base URL。 */
function findProviderDefaultBaseUrl(providerKey: string | null | undefined) {
  return providersQuery.data.value?.find(item => item.provider_key === providerKey)?.default_base_url ?? ''
}

/** 从供应商列表中查找默认模型 ID。 */
function findProviderDefaultModelId(providerKey: string | null | undefined) {
  return providersQuery.data.value?.find(item => item.provider_key === providerKey)?.default_model_id ?? ''
}

/** 从供应商列表中查找默认 thinking enabled。 */
function findProviderDefaultThinkingEnabled(providerKey: string | null | undefined) {
  return Boolean(providersQuery.data.value?.find(item => item.provider_key === providerKey)?.default_thinking_enabled)
}

/** 从供应商列表中查找默认 thinking effort。 */
function findProviderDefaultThinkingEffort(providerKey: string | null | undefined) {
  return providersQuery.data.value?.find(item => item.provider_key === providerKey)?.default_thinking_effort ?? null
}

/** 从供应商列表中查找默认图片输入能力。 */
function findProviderDefaultSupportsImageInput(providerKey: string | null | undefined) {
  return Boolean(providersQuery.data.value?.find(item => item.provider_key === providerKey)?.default_supports_image_input)
}

/** 判断 token 字段是否仍是默认值，可在切换供应商时替换。 */
function shouldReplaceTokenDefault(value: number, providerKey: string | null | undefined, kind: 'context' | 'output') {
  const provider = providersQuery.data.value?.find(item => item.provider_key === providerKey)
  const previousDefault = kind === 'context'
    ? provider?.default_context_window_tokens ?? DEFAULT_CONTEXT_WINDOW_TOKENS
    : provider?.default_max_output_tokens ?? DEFAULT_MAX_OUTPUT_TOKENS
  return value === previousDefault
}

/** 返回智能体模型绑定状态文案。 */
function getAgentSlotLabel(agent: AgentConfigItem) {
  const slot = slotsQuery.data.value?.find(item => item.slot === agent.llm_slot)
  if (!agent.llm_slot) return '无绑定'
  if (!slot) return '绑定项未知'
  return slot.binding_ready ? slot.llm_config_name ?? '已绑定' : '需绑定'
}

/** 返回智能体模型绑定状态样式。 */
function getAgentSlotClass(agent: AgentConfigItem) {
  const slot = slotsQuery.data.value?.find(item => item.slot === agent.llm_slot)
  if (slot?.binding_ready) return 'bg-emerald-50 text-emerald-700'
  return 'bg-amber-50 text-amber-700'
}

/** 用服务端配置重置工具草稿。 */
function resetToolDrafts(config: AgentConfigItem) {
  for (const key of Object.keys(toolDrafts)) {
    delete toolDrafts[key]
  }
  for (const group of config.tool_groups) {
    for (const tool of group.tools) {
      toolDrafts[tool.key] = {
        enabled: tool.enabled,
        descriptionOverride: tool.description_override ?? '',
        instructionsOverride: tool.instructions_override ?? '',
      }
    }
  }
}

/** 重置工具组展开状态，默认全部折叠。 */
function resetGroupExpansion(config: AgentConfigItem) {
  for (const key of Object.keys(expandedGroupKeys)) {
    delete expandedGroupKeys[key]
  }
  for (const group of config.tool_groups) {
    expandedGroupKeys[group.key] = false
  }
}

/** 统计工具组内当前草稿启用的工具数量。 */
function getToolGroupEnabledCount(group: AgentToolGroupConfigItem) {
  return group.tools.filter(tool => toolDrafts[tool.key]?.enabled ?? tool.enabled).length
}

/** 切换工具组展开状态。 */
function toggleToolGroup(groupKey: string) {
  expandedGroupKeys[groupKey] = !expandedGroupKeys[groupKey]
}

/** 判断工具组是否处于展开状态。 */
function isToolGroupExpanded(groupKey: string) {
  return expandedGroupKeys[groupKey] === true
}

/** 切换单个工具的详细编辑行。 */
function toggleToolEditor(toolKey: string) {
  editingToolKey.value = editingToolKey.value === toolKey ? null : toolKey
}

/** 保存当前智能体的模型绑定。 */
async function handleSaveSelectedAgentSlot(scope: AiLlmConfigScope = 'personal') {
  const slot = selectedAgentConfig.value?.llm_slot
  if (!slot) {
    Message.error('当前智能体没有可用的模型绑定项。')
    return
  }
  const selectedModelId = slotDrafts[slot] ?? null
  if (scope === 'global') {
    const selected = configsQuery.data.value?.find(config => config.id === selectedModelId)
    if (!selected || selected.scope !== 'global') {
      Message.error('全局默认槽位只能绑定管理员全局模型。')
      return
    }
  }
  bindingSlot.value = scope === 'global' ? `global:${slot}` : slot
  try {
    await updateLlmSlotBinding(slot, selectedModelId, scope)
    await refreshLlmQueries()
    Message.success(scope === 'global' ? '全局默认模型已保存。' : '模型绑定已保存。')
  } catch (error) {
    Message.error(getErrorMessage(error, '保存模型绑定失败。'))
  } finally {
    bindingSlot.value = null
  }
}

/** 保存当前智能体的完整提示词。 */
async function handleSavePrompt() {
  if (!selectedAgentConfig.value) return
  savingPrompt.value = true
  try {
    const normalizedPrompt = promptDraft.value.trim()
    await updateAgentConfig(selectedAgentConfig.value.id, {
      prompt_override: normalizedPrompt || null,
    })
    await refreshAgentQueries()
    Message.success('智能体提示词已保存。')
  } catch (error) {
    Message.error(getErrorMessage(error, '保存智能体提示词失败。'))
  } finally {
    savingPrompt.value = false
  }
}

/** 恢复当前智能体默认完整提示词。 */
async function handleRestorePrompt() {
  if (!selectedAgentConfig.value) return
  savingPrompt.value = true
  try {
    await updateAgentConfig(selectedAgentConfig.value.id, { prompt_override: null })
    await refreshAgentQueries()
    Message.success('智能体提示词已恢复默认。')
  } catch (error) {
    Message.error(getErrorMessage(error, '恢复智能体提示词失败。'))
  } finally {
    savingPrompt.value = false
  }
}

/** 保存单个工具的启停状态与说明覆盖。 */
async function handleSaveTool(tool: AgentToolConfigItem) {
  if (!selectedAgentConfig.value || !toolDrafts[tool.key]) return
  const draft = toolDrafts[tool.key]
  savingToolKey.value = tool.key
  try {
    await updateAgentToolConfig(selectedAgentConfig.value.id, tool.key, {
      enabled: draft.enabled,
      description_override: draft.descriptionOverride.trim() || null,
      instructions_override: draft.instructionsOverride.trim() || null,
    })
    await refreshAgentQueries()
    Message.success('工具配置已保存。')
  } catch (error) {
    Message.error(getErrorMessage(error, '保存工具配置失败。'))
  } finally {
    savingToolKey.value = null
  }
}

/** 恢复单个工具默认配置。 */
async function handleRestoreTool(tool: AgentToolConfigItem) {
  if (!selectedAgentConfig.value) return
  savingToolKey.value = tool.key
  try {
    await updateAgentToolConfig(selectedAgentConfig.value.id, tool.key, { restore_default: true })
    await refreshAgentQueries()
    Message.success('工具配置已恢复默认。')
  } catch (error) {
    Message.error(getErrorMessage(error, '恢复工具配置失败。'))
  } finally {
    savingToolKey.value = null
  }
}

/** 判断工具草稿是否发生变化。 */
function isToolDirty(tool: AgentToolConfigItem) {
  const draft = toolDrafts[tool.key]
  if (!draft) return false
  return draft.enabled !== tool.enabled
    || draft.descriptionOverride.trim() !== (tool.description_override ?? '')
    || draft.instructionsOverride.trim() !== (tool.instructions_override ?? '')
}

/** 判断工具说明或提示词是否已经被覆盖。 */
function isToolCustomized(tool: AgentToolConfigItem) {
  return Boolean(tool.description_override || tool.instructions_override)
}

/** 返回工具风险级别标签文案。 */
function getRiskLabel(tool: AgentToolConfigItem) {
  if (!tool.configurable) return '系统工具'
  if (tool.requires_confirmation) return '确认执行'
  if (tool.risk_level === 'write') return '写入工具'
  return '只读工具'
}

/** 返回工具风险级别样式。 */
function getRiskClass(riskLevel: AgentToolConfigItem['risk_level']) {
  if (riskLevel === 'danger') return 'bg-rose-50 text-rose-700'
  if (riskLevel === 'write') return 'bg-amber-50 text-amber-700'
  if (riskLevel === 'system') return 'bg-slate-100 text-slate-500'
  return 'bg-emerald-50 text-emerald-700'
}

/** 将 Agent 工具说明中的列表字段格式化为紧凑文案。 */
function formatGuideList(items: string[], emptyText: string) {
  return items.length ? items.join('、') : emptyText
}

/** 将 Agent 工具说明中的 JSON 数据格式化为只读代码块。 */
function formatGuideJson(value: unknown) {
  return JSON.stringify(value, null, 2)
}

/** 判断工具说明是否提供返回示例。 */
function hasGuideResponseExample(tool: AgentToolConfigItem) {
  return tool.agent_guide.response_example !== null && tool.agent_guide.response_example !== undefined
}

/** 按范围选择默认供应商配置，优先使用 DeepSeek。 */
function findDefaultProviderConfigForScope(scope: AiLlmConfigScope) {
  const candidates = (providerConfigsQuery.data.value ?? []).filter(config => config.scope === scope && config.status === 'active')
  return candidates.find(config => config.provider_key === DEFAULT_NEW_MODEL_PROVIDER_KEY) ?? candidates[0] ?? null
}

/** 根据供应商配置找到静态目录项。 */
function findProviderForConfig(config: LlmProviderConfigItem | null) {
  return providersQuery.data.value?.find(provider => provider.provider_key === config?.provider_key) ?? null
}

/** 重置供应商表单并切换到新建状态。 */
function resetProviderForm() {
  activeSection.value = 'providers'
  providerPanelMode.value = 'create'
  providerCreateRequested.value = true
  selectedProviderConfigId.value = null
  providerForm.scope = 'personal'
  providerForm.name = ''
  const provider = providersQuery.data.value?.length
    ? findDefaultNewModelProvider(providersQuery.data.value)
    : null
  providerForm.provider_key = provider?.provider_key ?? null
  providerForm.api_key = ''
  prefillProviderFormFromProvider(provider)
}

/** 把已有供应商配置装载到右侧表单。 */
async function handleEditProviderConfig(config: LlmProviderConfigItem) {
  activeSection.value = 'providers'
  providerPanelMode.value = 'detail'
  providerCreateRequested.value = false
  applyingExistingProviderConfig.value = true
  selectedProviderConfigId.value = config.id
  providerForm.scope = config.scope
  providerForm.name = config.name
  providerForm.provider_key = config.provider_key
  providerForm.base_url = config.base_url ?? ''
  providerForm.api_key = ''
  await nextTick()
  applyingExistingProviderConfig.value = false
}

/** 从供应商详情进入编辑态。 */
function handleStartEditProviderConfig() {
  if (!selectedProviderConfig.value?.editable) {
    Message.error('管理员全局供应商只读，不能由当前用户修改。')
    return
  }
  providerPanelMode.value = 'edit'
}

/** 取消供应商编辑，重新装载详情数据以丢弃草稿。 */
function handleCancelProviderEdit() {
  const config = selectedProviderConfig.value
  if (!config) {
    resetProviderForm()
    return
  }
  void handleEditProviderConfig(config)
}

/** 重置模型表单并切换到新建状态。 */
function resetModelForm() {
  activeSection.value = 'models'
  modelPanelMode.value = 'create'
  modelCreateRequested.value = true
  selectedConfigId.value = null
  modelForm.scope = 'personal'
  modelForm.name = ''
  const providerConfig = findDefaultProviderConfigForScope(modelForm.scope)
  modelForm.provider_config_id = providerConfig?.id ?? null
  const provider = findProviderForConfig(providerConfig)
  prefillModelFormFromProvider(provider)
  modelForm.history_token_ratio = 0.5
  modelForm.compression_target_ratio = DEFAULT_COMPRESSION_TARGET_RATIO
  advancedConfigText.value = '{}'
  advancedConfigError.value = ''
  advancedConfigCollapsed.value = true
}

/** 把已有模型装载到右侧表单。 */
async function handleEditModel(config: LlmConfigItem) {
  activeSection.value = 'models'
  modelPanelMode.value = 'detail'
  modelCreateRequested.value = false
  applyingExistingModel.value = true
  selectedConfigId.value = config.id
  modelForm.scope = config.scope
  modelForm.name = config.name
  modelForm.provider_config_id = config.provider_config_id
  modelForm.model_id = config.model_id
  modelForm.thinking_enabled = config.thinking_enabled
  modelForm.thinking_effort = config.thinking_effort
  modelForm.supports_image_input = config.supports_image_input
  modelForm.context_window_tokens = config.context_window_tokens
  modelForm.max_output_tokens = config.max_output_tokens
  modelForm.history_token_ratio = config.history_token_ratio
  modelForm.compression_target_ratio = config.compression_target_ratio
  advancedConfigText.value = JSON.stringify(config.advanced_config_json ?? {}, null, 2)
  advancedConfigError.value = ''
  advancedConfigCollapsed.value = true
  await nextTick()
  applyingExistingModel.value = false
}

/** 从模型详情进入编辑态。 */
function handleStartEditModel() {
  if (!selectedModel.value?.editable) {
    Message.error('管理员全局模型只读，不能由当前用户修改。')
    return
  }
  modelPanelMode.value = 'edit'
}

/** 取消模型编辑，重新装载详情数据以丢弃草稿。 */
function handleCancelModelEdit() {
  const config = selectedModel.value
  if (!config) {
    resetModelForm()
    return
  }
  void handleEditModel(config)
}

/** 解析高级 JSON 配置并同步错误提示。 */
function parseAdvancedConfig() {
  const rawText = advancedConfigText.value.trim() || '{}'
  try {
    const parsed = JSON.parse(rawText) as Record<string, unknown>
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      throw new Error('高级 JSON 配置必须是对象。')
    }
    advancedConfigError.value = ''
    return parsed
  } catch (error) {
    advancedConfigError.value = error instanceof Error ? error.message : '高级 JSON 配置格式不正确。'
    throw error
  }
}

/** 格式化高级 JSON 配置。 */
function formatAdvancedConfig() {
  try {
    advancedConfigText.value = JSON.stringify(parseAdvancedConfig(), null, 2)
    advancedConfigCollapsed.value = false
  } catch {
    Message.error('当前高级 JSON 不合法，无法格式化。')
  }
}

/** 归一化 token 数配置，避免空值或非法值提交到后端。 */
function normalizePositiveInteger(value: number, fallback: number) {
  const normalized = Math.floor(Number(value))
  return Number.isFinite(normalized) && normalized > 0 ? normalized : fallback
}

/** 将历史比例限制在后端允许范围内。 */
function normalizeHistoryRatio(value: number) {
  const normalized = Number(value)
  if (!Number.isFinite(normalized)) {
    return 0.5
  }
  return Math.min(0.9, Math.max(0, normalized))
}

/** 将压缩目标比例限制在后端允许范围内。 */
function normalizeCompressionTargetRatio(value: number) {
  const normalized = Number(value)
  if (!Number.isFinite(normalized)) {
    return DEFAULT_COMPRESSION_TARGET_RATIO
  }
  return Math.min(0.5, Math.max(0.02, normalized))
}

/** 创建或更新供应商配置。 */
async function handleSubmitProviderConfig() {
  if (selectedProviderConfig.value && !selectedProviderConfig.value.editable) {
    Message.error('管理员全局供应商只读，不能由当前用户修改。')
    return
  }
  const providerKey = providerForm.provider_key
  if (!providerForm.name.trim() || !providerKey) {
    Message.error('请先填写供应商配置名称和供应商。')
    return
  }

  const provider = currentProviderForProviderForm.value
  const baseUrl = provider?.supports_base_url ? providerForm.base_url.trim() || null : null
  const apiKey = provider?.supports_api_key ? providerForm.api_key.trim() || null : null

  savingProviderConfig.value = true
  try {
    if (selectedProviderConfigId.value) {
      const updatePayload: LlmProviderConfigUpdatePayload = {
        name: providerForm.name.trim(),
        base_url: baseUrl,
      }
      if (apiKey) {
        updatePayload.api_key = apiKey
      }
      const updatedProviderConfig = await updateLlmProviderConfig(selectedProviderConfigId.value, updatePayload)
      queryClient.setQueryData<LlmProviderConfigItem[]>(['llm-provider-configs'], currentItems => (
        currentItems?.map(item => item.id === updatedProviderConfig.id ? updatedProviderConfig : item) ?? [updatedProviderConfig]
      ))
      await handleEditProviderConfig(updatedProviderConfig)
      Message.success('供应商已更新。')
    } else {
      const createdProviderConfig = await createLlmProviderConfig({
        name: providerForm.name.trim(),
        scope: providerForm.scope,
        provider_key: providerKey,
        base_url: baseUrl,
        api_key: apiKey,
      })
      queryClient.setQueryData<LlmProviderConfigItem[]>(['llm-provider-configs'], currentItems => [
        createdProviderConfig,
        ...(currentItems ?? []).filter(item => item.id !== createdProviderConfig.id),
      ])
      await handleEditProviderConfig(createdProviderConfig)
      Message.success('供应商已创建。')
    }
    await refreshProviderQueries()
  } catch (error) {
    Message.error(getErrorMessage(error, '保存供应商失败。'))
  } finally {
    savingProviderConfig.value = false
  }
}

/** 创建或更新模型。 */
async function handleSubmitModel() {
  if (selectedModel.value && !selectedModel.value.editable) {
    Message.error('管理员全局模型只读，不能由当前用户修改。')
    return
  }
  const providerConfigId = modelForm.provider_config_id
  if (!modelForm.name.trim() || !providerConfigId || !modelForm.model_id.trim()) {
    Message.error('请先填写模型名称、供应商配置和模型 ID。')
    return
  }

  let advancedConfig: Record<string, unknown>
  try {
    advancedConfig = parseAdvancedConfig()
  } catch {
    Message.error('高级 JSON 配置不合法。')
    return
  }

  savingConfig.value = true
  try {
    if (selectedConfigId.value) {
      const updatePayload: LlmConfigUpdatePayload = {
        name: modelForm.name.trim(),
        provider_config_id: providerConfigId,
        model_id: modelForm.model_id.trim(),
        thinking_enabled: modelForm.thinking_enabled,
        thinking_effort: modelForm.thinking_effort,
        supports_image_input: modelForm.supports_image_input,
        context_window_tokens: normalizePositiveInteger(modelForm.context_window_tokens, DEFAULT_CONTEXT_WINDOW_TOKENS),
        max_output_tokens: normalizePositiveInteger(modelForm.max_output_tokens, DEFAULT_MAX_OUTPUT_TOKENS),
        history_token_ratio: normalizeHistoryRatio(modelForm.history_token_ratio),
        compression_target_ratio: normalizeCompressionTargetRatio(modelForm.compression_target_ratio),
        advanced_config_json: advancedConfig,
      }
      const updatedConfig = await updateLlmConfig(selectedConfigId.value, updatePayload)
      queryClient.setQueryData<LlmConfigItem[]>(['llm-configs'], currentItems => (
        currentItems?.map(item => item.id === updatedConfig.id ? updatedConfig : item) ?? [updatedConfig]
      ))
      await handleEditModel(updatedConfig)
      Message.success('模型已更新。')
    } else {
      const createdConfig = await createLlmConfig({
        name: modelForm.name.trim(),
        scope: modelForm.scope,
        provider_config_id: providerConfigId,
        model_id: modelForm.model_id.trim(),
        thinking_enabled: modelForm.thinking_enabled,
        thinking_effort: modelForm.thinking_effort,
        supports_image_input: modelForm.supports_image_input,
        context_window_tokens: normalizePositiveInteger(modelForm.context_window_tokens, DEFAULT_CONTEXT_WINDOW_TOKENS),
        max_output_tokens: normalizePositiveInteger(modelForm.max_output_tokens, DEFAULT_MAX_OUTPUT_TOKENS),
        history_token_ratio: normalizeHistoryRatio(modelForm.history_token_ratio),
        compression_target_ratio: normalizeCompressionTargetRatio(modelForm.compression_target_ratio),
        advanced_config_json: advancedConfig,
      })
      queryClient.setQueryData<LlmConfigItem[]>(['llm-configs'], currentItems => [
        createdConfig,
        ...(currentItems ?? []).filter(item => item.id !== createdConfig.id),
      ])
      await handleEditModel(createdConfig)
      Message.success('模型已创建。')
    }
    await refreshLlmQueries()
  } catch (error) {
    Message.error(getErrorMessage(error, '保存模型失败。'))
  } finally {
    savingConfig.value = false
  }
}

/** 删除供应商配置；后端会拒绝仍有关联模型的供应商。 */
async function handleDeleteProviderConfig(config: LlmProviderConfigItem) {
  const confirmed = await createConfirm(
    `确认删除供应商「${config.name}」吗？删除前必须先删除所有关联模型。`,
    '删除供应商',
  )
  if (!confirmed) {
    return
  }

  deletingProviderConfigId.value = config.id
  try {
    await deleteLlmProviderConfig(config.id)
    const remainingProviderConfigs = (providerConfigsQuery.data.value ?? []).filter(item => item.id !== config.id)
    queryClient.setQueryData<LlmProviderConfigItem[]>(['llm-provider-configs'], remainingProviderConfigs)
    if (selectedProviderConfigId.value === config.id) {
      selectedProviderConfigId.value = null
      providerCreateRequested.value = false
      const nextProviderConfig = remainingProviderConfigs[0]
      if (nextProviderConfig) {
        await handleEditProviderConfig(nextProviderConfig)
      } else {
        resetProviderForm()
      }
    }
    Message.success('供应商已删除。')
    await refreshProviderQueries()
  } catch (error) {
    Message.error(getErrorMessage(error, '删除供应商失败。'))
  } finally {
    deletingProviderConfigId.value = null
  }
}

/** 删除模型配置；引用该模型的槽位会被后端自动解绑。 */
async function handleDeleteModel(config: LlmConfigItem) {
  const confirmed = await createConfirm(
    `确认删除模型「${config.name}」吗？删除后已关联会话无法继续发起运行，相关模型绑定会自动移除。`,
    '删除模型',
  )
  if (!confirmed) {
    return
  }

  deletingConfigId.value = config.id
  try {
    await deleteLlmConfig(config.id)
    const remainingConfigs = (configsQuery.data.value ?? []).filter(item => item.id !== config.id)
    queryClient.setQueryData<LlmConfigItem[]>(['llm-configs'], remainingConfigs)
    if (selectedConfigId.value === config.id) {
      selectedConfigId.value = null
      modelCreateRequested.value = false
      const nextModel = remainingConfigs[0]
      if (nextModel) {
        await handleEditModel(nextModel)
      } else {
        resetModelForm()
      }
    }
    Message.success('模型已删除。')
    await refreshLlmQueries()
  } catch (error) {
    Message.error(getErrorMessage(error, '删除模型失败。'))
  } finally {
    deletingConfigId.value = null
  }
}

/** 刷新模型、模型绑定与运行入口相关缓存。 */
async function refreshLlmQueries() {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ['llm-configs'] }),
    queryClient.invalidateQueries({ queryKey: ['llm-provider-configs'] }),
    queryClient.invalidateQueries({ queryKey: ['llm-slots'] }),
    queryClient.invalidateQueries({ queryKey: ['ai-agents'] }),
  ])
}

/** 刷新供应商、模型绑定与运行入口相关缓存。 */
async function refreshProviderQueries() {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ['llm-provider-configs'] }),
    queryClient.invalidateQueries({ queryKey: ['llm-configs'] }),
    queryClient.invalidateQueries({ queryKey: ['llm-slots'] }),
    queryClient.invalidateQueries({ queryKey: ['ai-agents'] }),
  ])
}

/** 刷新智能体配置及运行入口相关缓存。 */
async function refreshAgentQueries() {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ['agent-configs'] }),
    queryClient.invalidateQueries({ queryKey: ['agent-catalog'] }),
    queryClient.invalidateQueries({ queryKey: ['ai-agents'] }),
  ])
}
</script>

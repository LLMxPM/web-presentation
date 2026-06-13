<!-- 文件功能：整合账号级 AI 设置，集中管理智能体模型绑定、提示词、工具配置与模型。 -->
<template>
  <div class="space-y-5 pb-10">
    <header class="rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div class="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
            <Bot class="h-4 w-4" />
            <span>账户 AI 设置</span>
          </div>
          <h1 class="mt-2 text-2xl font-bold tracking-tight text-slate-900">AI 设置</h1>
        </div>
        <dl class="grid min-w-[520px] grid-cols-4 overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 text-center">
          <div class="border-r border-slate-200 px-4 py-3">
            <dt class="text-[11px] font-semibold text-slate-400">智能体</dt>
            <dd class="mt-1 text-lg font-bold text-slate-900">{{ agentCount }}</dd>
          </div>
          <div class="border-r border-slate-200 px-4 py-3">
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

    <section class="grid gap-5 xl:grid-cols-[420px_minmax(0,1fr)]">
      <aside class="min-h-[720px] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div class="border-b border-slate-200 p-3">
          <div class="grid grid-cols-2 rounded-xl bg-slate-100 p-1">
            <button
              type="button"
              class="h-9 rounded-lg text-xs font-bold transition"
              :class="activeSection === 'agents' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-800'"
              @click="activeSection = 'agents'"
            >
              智能体配置
            </button>
            <button
              type="button"
              class="h-9 rounded-lg text-xs font-bold transition"
              :class="activeSection === 'models' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-800'"
              @click="activeSection = 'models'"
            >
              模型
            </button>
          </div>
        </div>

        <div v-if="activeSection === 'agents'" class="max-h-[calc(100vh-230px)] overflow-y-auto p-3">
          <div v-if="configsQuery.isFetching.value && !(agentConfigsQuery.data.value?.length)" class="rounded-xl border border-dashed border-slate-200 px-4 py-10 text-center text-sm text-slate-400">
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

        <div v-else class="max-h-[calc(100vh-230px)] overflow-y-auto p-3">
          <div class="mb-3 flex items-center justify-between gap-3">
            <p class="text-sm font-semibold text-slate-900">模型</p>
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
                  <p class="mt-1 truncate text-xs text-slate-500">{{ config.provider_label }} / {{ config.model_id }}</p>
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
                    {{ config.status === 'active' ? '启用' : '归档' }}
                  </span>
                </span>
              </div>
              <div class="mt-3 flex min-w-0 items-center justify-between gap-2">
                <code class="min-w-0 truncate rounded bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-600">{{ config.model_id }}</code>
                <span class="shrink-0 text-[11px] font-semibold" :class="config.has_api_key ? 'text-slate-500' : 'text-amber-600'">
                  {{ config.has_api_key ? config.api_key_masked : '未保存 API Key' }}
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
            <div class="flex flex-wrap gap-2">
              <span class="rounded-full px-3 py-1 text-xs font-semibold" :class="getAgentSlotClass(selectedAgentConfig)">
                {{ getAgentSlotLabel(selectedAgentConfig) }}
              </span>
            </div>
          </div>

          <article class="rounded-xl border border-slate-200 bg-slate-50 p-4">
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
              <div class="flex min-w-[420px] items-center gap-2">
                <SearchableSelect
                  v-if="selectedAgentConfig.llm_slot"
                  v-model="slotDrafts[selectedAgentConfig.llm_slot]"
                  :options="configOptions"
                  clearable
                  size="compact"
                  placeholder="选择模型"
                />
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
          </article>

          <section class="grid gap-4 2xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <BaseInput
              :model-value="selectedAgentConfig.system_prompt"
              type="textarea"
              label="平台底线提示词"
              :rows="10"
              disabled
            />
            <div class="space-y-3">
              <BaseInput
                v-model="promptDraft"
                type="textarea"
                label="业务补充提示词"
                :rows="10"
                placeholder="输入当前账号下的业务补充提示词"
              />
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

          <section v-if="selectedAgentConfig.team_members.length" class="space-y-3">
            <div>
              <h3 class="text-sm font-bold text-slate-900">Team 成员描述</h3>
              <p class="mt-1 text-xs text-slate-500">描述会进入内容助手 Team 的成员上下文，影响主助手何时调度对应成员。</p>
            </div>
            <article
              v-for="member in selectedAgentConfig.team_members"
              :key="member.id"
              class="rounded-xl border border-slate-200 bg-slate-50 p-4"
            >
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div class="flex min-w-0 items-start gap-3">
                  <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ring-1" :class="getAgentIconShellClass(member.icon, false)">
                    <component :is="resolveAgentIconComponent(member.icon)" class="h-4 w-4" />
                  </span>
                  <div class="min-w-0">
                    <p class="text-sm font-bold text-slate-900">{{ member.name }}</p>
                    <p class="mt-1 text-xs text-slate-500">{{ member.description_customized ? '描述已覆盖' : '默认描述' }}</p>
                  </div>
                </div>
                <div class="flex shrink-0 gap-2">
                  <BaseButton
                    variant="ghost"
                    size="sm"
                    :loading="savingTeamMemberId === member.id"
                    @click="handleRestoreTeamMember(member)"
                  >
                    恢复默认
                  </BaseButton>
                  <BaseButton
                    variant="primary"
                    size="sm"
                    :loading="savingTeamMemberId === member.id"
                    :disabled="!isTeamMemberDirty(member)"
                    @click="handleSaveTeamMember(member)"
                  >
                    保存描述
                  </BaseButton>
                </div>
              </div>
              <BaseInput
                v-if="teamMemberDrafts[member.id] !== undefined"
                v-model="teamMemberDrafts[member.id]"
                class="mt-3"
                type="textarea"
                label="成员描述"
                :rows="3"
                :placeholder="member.default_description"
              />
            </article>
          </section>

          <section class="space-y-3">
            <div class="flex items-center justify-between gap-3">
              <div>
                <h3 class="text-sm font-bold text-slate-900">工具配置</h3>
                <p class="mt-1 text-xs text-slate-500">工具组默认折叠，展开后可批量启停或编辑单个工具说明。</p>
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
                class="flex w-full items-center justify-between gap-3 bg-slate-50 px-4 py-3 text-left transition hover:bg-slate-100"
                @click="toggleToolGroup(group.key)"
              >
                <span class="min-w-0">
                  <span class="flex items-center gap-2">
                    <component :is="isToolGroupExpanded(group.key) ? ChevronDown : ChevronRight" class="h-4 w-4 text-slate-400" />
                    <span class="text-sm font-bold text-slate-900">{{ group.label }}</span>
                    <span class="text-xs text-slate-400">{{ group.tools.length }} 个工具</span>
                  </span>
                  <span class="ml-6 mt-1 block truncate text-xs text-slate-500">{{ group.description }}</span>
                </span>
                <span v-if="group.tools.some(tool => tool.configurable)" class="flex shrink-0 gap-2" @click.stop>
                  <BaseButton variant="ghost" size="sm" :loading="savingGroupKey === group.key" @click="handleSetGroupEnabled(group, true)">
                    全部开启
                  </BaseButton>
                  <BaseButton variant="ghost" size="sm" :loading="savingGroupKey === group.key" @click="handleSetGroupEnabled(group, false)">
                    全部关闭
                  </BaseButton>
                </span>
              </button>

              <div v-show="isToolGroupExpanded(group.key)" class="overflow-x-auto">
                <table class="min-w-full table-fixed text-left text-xs">
                  <thead class="border-t border-slate-200 bg-white text-[11px] font-semibold text-slate-400">
                    <tr>
                      <th class="w-[34%] px-4 py-2">工具</th>
                      <th class="w-[14%] px-4 py-2">风险</th>
                      <th class="w-[14%] px-4 py-2">状态</th>
                      <th class="w-[16%] px-4 py-2">定制</th>
                      <th class="w-[22%] px-4 py-2 text-right">操作</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-100">
                    <template v-for="tool in group.tools" :key="tool.key">
                      <tr class="bg-white">
                        <td class="px-4 py-3">
                          <p class="font-semibold text-slate-900">{{ tool.label }}</p>
                          <code class="mt-1 block truncate text-[11px] text-slate-400">{{ tool.key }}</code>
                        </td>
                        <td class="px-4 py-3">
                          <span class="rounded-full px-2 py-0.5 text-[11px] font-semibold" :class="getRiskClass(tool.risk_level)">
                            {{ getRiskLabel(tool) }}
                          </span>
                        </td>
                        <td class="px-4 py-3">
                          <label v-if="tool.configurable && toolDrafts[tool.key]" class="inline-flex items-center gap-2">
                            <input
                              v-model="toolDrafts[tool.key].enabled"
                              type="checkbox"
                              class="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                            >
                            <span class="font-semibold" :class="toolDrafts[tool.key].enabled ? 'text-emerald-700' : 'text-slate-400'">
                              {{ toolDrafts[tool.key].enabled ? '启用' : '关闭' }}
                            </span>
                          </label>
                          <span v-else class="inline-flex items-center gap-1 text-slate-400">
                            <Lock class="h-3.5 w-3.5" />
                            系统只读
                          </span>
                        </td>
                        <td class="px-4 py-3 text-slate-500">
                          {{ isToolCustomized(tool) ? '已覆盖' : '默认' }}
                        </td>
                        <td class="px-4 py-3">
                          <div class="flex justify-end gap-2">
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
                        </td>
                      </tr>
                      <tr v-if="editingToolKey === tool.key" class="bg-slate-50">
                        <td colspan="5" class="px-4 py-4">
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

                          <section class="mt-4 space-y-4 rounded-xl border border-slate-200 bg-white p-4">
                            <div class="flex flex-wrap items-start justify-between gap-3">
                              <div>
                                <h4 class="text-sm font-bold text-slate-900">Agent 完整说明</h4>
                                <p class="mt-1 text-xs leading-5 text-slate-500">{{ tool.agent_guide.effective_description }}</p>
                              </div>
                              <div class="flex flex-wrap gap-2">
                                <code class="rounded bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-600">{{ tool.agent_guide.tool_name }}</code>
                                <span class="rounded-full px-2 py-1 text-[11px] font-semibold" :class="getRiskClass(tool.agent_guide.risk_level)">
                                  {{ getRiskLabel(tool) }}
                                </span>
                              </div>
                            </div>

                            <dl class="grid gap-3 text-xs md:grid-cols-2">
                              <div class="rounded-lg bg-slate-50 p-3">
                                <dt class="font-semibold text-slate-400">系统默认说明</dt>
                                <dd class="mt-1 leading-5 text-slate-700">{{ tool.agent_guide.system_description }}</dd>
                              </div>
                              <div class="rounded-lg bg-slate-50 p-3">
                                <dt class="font-semibold text-slate-400">上下文要求</dt>
                                <dd class="mt-1 leading-5 text-slate-700">
                                  {{ formatGuideList(tool.agent_guide.required_context_fields, '无额外上下文字段') }}
                                </dd>
                              </div>
                              <div class="rounded-lg bg-slate-50 p-3">
                                <dt class="font-semibold text-slate-400">运行时披露组</dt>
                                <dd class="mt-1 leading-5 text-slate-700">
                                  {{ formatGuideList(tool.agent_guide.runtime_disclosure_groups, '不通过业务工具组披露') }}
                                </dd>
                              </div>
                              <div class="rounded-lg bg-slate-50 p-3">
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
                              <p v-else class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-xs text-slate-400">暂无返回示例</p>
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
                        </td>
                      </tr>
                    </template>
                  </tbody>
                </table>
              </div>
            </article>
          </section>
        </section>

        <section v-else-if="activeSection === 'agents'" class="flex min-h-[720px] items-center justify-center p-8 text-center text-sm text-slate-400">
          暂无可配置智能体。
        </section>

        <AccountAiModelDetail
          v-else
          v-model:advanced-config-text="advancedConfigText"
          v-model:advanced-config-collapsed="advancedConfigCollapsed"
          :form="modelForm"
          :selected-config-id="selectedConfigId"
          :selected-model="selectedModel"
          :current-provider="currentProvider"
          :provider-options="providerOptions"
          :advanced-config-error="advancedConfigError"
          :saving-config="savingConfig"
          :status-updating-config-id="statusUpdatingConfigId"
          :can-create-global="canCreateGlobal"
          @toggle-status="handleToggleModelStatus"
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
import { Bot, ChevronDown, ChevronRight, Lock, Plus } from '@lucide/vue'

import {
  createLlmConfig,
  listLlmConfigs,
  listLlmProviders,
  listLlmSlots,
  updateLlmConfig,
  updateLlmSlotBinding,
} from '@/api/llm'
import type { LlmConfigUpdatePayload } from '@/api/llm'
import {
  listAgentCatalog,
  listAgentConfigs,
  updateAgentConfig,
  updateAgentToolConfig,
} from '@/api/agent-config'
import { getErrorMessage } from '@/api/http'
import AccountAiModelDetail from '@/components/account-ai/AccountAiModelDetail.vue'
import { getAgentIconShellClass, resolveAgentIconComponent } from '@/components/agent/agent-icon'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import SearchableSelect from '@/components/ui/SearchableSelect.vue'
import type { SelectOption } from '@/components/ui/select'
import { useAuthStore } from '@/stores/auth'
import type {
  AiLlmConfigScope,
  AgentConfigItem,
  AgentTeamMemberConfigItem,
  AgentToolConfigItem,
  AgentToolGroupConfigItem,
  LlmConfigItem,
  LlmProviderCatalogItem,
} from '@/types/api'
import { Message } from '@/utils/message'

type ActiveSection = 'agents' | 'models'

const DEFAULT_CONTEXT_WINDOW_TOKENS = 128000
const DEFAULT_MAX_OUTPUT_TOKENS = 32000
const DEFAULT_COMPRESSION_TARGET_RATIO = 0.1
const DEFAULT_NEW_MODEL_PROVIDER_KEY = 'deepseek'

interface LlmFormState {
  scope: AiLlmConfigScope
  name: string
  provider_key: string | null
  model_id: string
  base_url: string
  api_key: string
  thinking_enabled: boolean
  thinking_effort: string | null
  supports_image_input: boolean
  context_window_tokens: number
  max_output_tokens: number
  history_token_ratio: number
  compression_target_ratio: number
}

interface ToolDraft {
  enabled: boolean
  descriptionOverride: string
  instructionsOverride: string
}

const queryClient = useQueryClient()
const authStore = useAuthStore()
const activeSection = ref<ActiveSection>('agents')

const selectedAgentId = ref('')
const promptDraft = ref('')
const savingPrompt = ref(false)
const savingTeamMemberId = ref<string | null>(null)
const savingToolKey = ref<string | null>(null)
const savingGroupKey = ref<string | null>(null)
const editingToolKey = ref<string | null>(null)
const toolDrafts = reactive<Record<string, ToolDraft>>({})
const teamMemberDrafts = reactive<Record<string, string>>({})
const expandedGroupKeys = reactive<Record<string, boolean>>({})
const slotDrafts = reactive<Record<string, number | null>>({})
const bindingSlot = ref<string | null>(null)

const selectedConfigId = ref<number | null>(null)
const advancedConfigText = ref('{}')
const advancedConfigError = ref('')
const advancedConfigCollapsed = ref(true)
const savingConfig = ref(false)
const statusUpdatingConfigId = ref<number | null>(null)
const applyingExistingModel = ref(false)

const modelForm = reactive<LlmFormState>({
  scope: 'personal',
  name: '',
  provider_key: null,
  model_id: '',
  base_url: '',
  api_key: '',
  thinking_enabled: false,
  thinking_effort: null,
  supports_image_input: false,
  context_window_tokens: DEFAULT_CONTEXT_WINDOW_TOKENS,
  max_output_tokens: DEFAULT_MAX_OUTPUT_TOKENS,
  history_token_ratio: 0.5,
  compression_target_ratio: DEFAULT_COMPRESSION_TARGET_RATIO,
})

const providersQuery = useQuery({
  queryKey: ['llm-providers'],
  queryFn: listLlmProviders,
})

const configsQuery = useQuery({
  queryKey: ['llm-configs'],
  queryFn: listLlmConfigs,
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
const activeModelCount = computed(() => (configsQuery.data.value ?? []).filter(config => config.status === 'active').length)
const unreadySlotCount = computed(() => (slotsQuery.data.value ?? []).filter(slot => !slot.binding_ready).length)
const allToolCount = computed(() => (
  (agentConfigsQuery.data.value ?? catalogQuery.data.value ?? [])
    .reduce((total, agent) => total + agent.tool_groups.reduce((groupTotal, group) => groupTotal + group.tools.length, 0), 0)
))
const canCreateGlobal = computed(() => authStore.user?.role === 'platform_admin')

const selectedAgentConfig = computed<AgentConfigItem | null>(() => (
  agentConfigsQuery.data.value?.find(item => item.id === selectedAgentId.value)
  ?? agentConfigsQuery.data.value?.[0]
  ?? null
))

const selectedModel = computed<LlmConfigItem | null>(() => (
  configsQuery.data.value?.find(item => item.id === selectedConfigId.value) ?? null
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

const providerOptions = computed<SelectOption[]>(() => (
  providersQuery.data.value?.map(provider => ({
    label: provider.label,
    value: provider.provider_key,
    description: provider.supports_thinking
      ? `支持 thinking · ${provider.thinking_mode}${provider.default_model_id ? ` · ${provider.default_model_id}` : ''}`
      : '不支持 thinking',
    keywords: [provider.provider_key, provider.agno_class_path],
  })) ?? []
))

const currentProvider = computed<LlmProviderCatalogItem | null>(() => (
  providersQuery.data.value?.find(provider => provider.provider_key === modelForm.provider_key) ?? null
))

const configOptions = computed<SelectOption[]>(() => (
  (configsQuery.data.value ?? [])
    .filter(config => config.status === 'active')
    .map(config => ({
      label: config.name,
      value: config.id,
      description: `${config.scope === 'global' ? '全局模型' : '个人模型'} · ${config.provider_label} / ${config.model_id}`,
      keywords: [config.provider_key, config.model_id, config.provider_label],
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
    resetTeamMemberDrafts(config)
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
    if (!modelForm.provider_key && providers?.length) {
      const provider = findDefaultNewModelProvider(providers)
      modelForm.provider_key = provider.provider_key
      prefillModelFormFromProvider(provider)
    }
  },
  { immediate: true },
)

watch(
  () => modelForm.provider_key,
  (providerKey, previousProviderKey) => {
    const provider = providersQuery.data.value?.find(item => item.provider_key === providerKey) ?? null
    if (!provider || applyingExistingModel.value) {
      return
    }
    if (providerKey !== previousProviderKey && (!modelForm.model_id || modelForm.model_id === findProviderDefaultModelId(previousProviderKey))) {
      modelForm.model_id = provider.default_model_id ?? ''
    }
    if (providerKey !== previousProviderKey && (!modelForm.base_url || modelForm.base_url === findProviderDefaultBaseUrl(previousProviderKey))) {
      modelForm.base_url = provider.default_base_url ?? ''
    }
    if (!provider.supports_thinking) {
      modelForm.thinking_enabled = false
      modelForm.thinking_effort = null
    } else {
      if (
        providerKey !== previousProviderKey
        && modelForm.thinking_enabled === findProviderDefaultThinkingEnabled(previousProviderKey)
      ) {
        modelForm.thinking_enabled = provider.default_thinking_enabled
      }
      if (!modelForm.thinking_effort || modelForm.thinking_effort === findProviderDefaultThinkingEffort(previousProviderKey)) {
        modelForm.thinking_effort = provider.default_thinking_effort ?? null
      }
    }
    if (
      providerKey !== previousProviderKey
      && modelForm.supports_image_input === findProviderDefaultSupportsImageInput(previousProviderKey)
    ) {
      modelForm.supports_image_input = provider.default_supports_image_input
    }
    if (
      providerKey !== previousProviderKey
      && shouldReplaceTokenDefault(modelForm.context_window_tokens, previousProviderKey, 'context')
    ) {
      modelForm.context_window_tokens = provider.default_context_window_tokens ?? DEFAULT_CONTEXT_WINDOW_TOKENS
    }
    if (
      providerKey !== previousProviderKey
      && shouldReplaceTokenDefault(modelForm.max_output_tokens, previousProviderKey, 'output')
    ) {
      modelForm.max_output_tokens = provider.default_max_output_tokens ?? DEFAULT_MAX_OUTPUT_TOKENS
    }
    if (!provider.supports_base_url) {
      modelForm.base_url = ''
    }
    if (!provider.supports_api_key) {
      modelForm.api_key = ''
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
  modelForm.base_url = provider?.supports_base_url ? provider.default_base_url ?? '' : ''
  modelForm.thinking_enabled = Boolean(provider?.supports_thinking && provider.default_thinking_enabled)
  modelForm.thinking_effort = provider?.supports_thinking ? provider.default_thinking_effort ?? null : null
  modelForm.supports_image_input = Boolean(provider?.default_supports_image_input)
  modelForm.context_window_tokens = provider?.default_context_window_tokens ?? DEFAULT_CONTEXT_WINDOW_TOKENS
  modelForm.max_output_tokens = provider?.default_max_output_tokens ?? DEFAULT_MAX_OUTPUT_TOKENS
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

/** 用服务端配置重置 Team 成员描述草稿。 */
function resetTeamMemberDrafts(config: AgentConfigItem) {
  for (const key of Object.keys(teamMemberDrafts)) {
    delete teamMemberDrafts[key]
  }
  for (const member of config.team_members) {
    teamMemberDrafts[member.id] = member.description
  }
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

/** 保存当前智能体的业务补充提示词。 */
async function handleSavePrompt() {
  if (!selectedAgentConfig.value) return
  savingPrompt.value = true
  try {
    const normalizedPrompt = promptDraft.value.trim()
    await updateAgentConfig(selectedAgentConfig.value.id, normalizedPrompt ? {
      prompt_override: normalizedPrompt,
    } : {
      restore_default: true,
    })
    await refreshAgentQueries()
    Message.success('智能体提示词已保存。')
  } catch (error) {
    Message.error(getErrorMessage(error, '保存智能体提示词失败。'))
  } finally {
    savingPrompt.value = false
  }
}

/** 恢复当前智能体默认业务补充提示词。 */
async function handleRestorePrompt() {
  if (!selectedAgentConfig.value) return
  savingPrompt.value = true
  try {
    await updateAgentConfig(selectedAgentConfig.value.id, { restore_default: true })
    await refreshAgentQueries()
    Message.success('智能体提示词已恢复默认。')
  } catch (error) {
    Message.error(getErrorMessage(error, '恢复智能体提示词失败。'))
  } finally {
    savingPrompt.value = false
  }
}

/** 保存 Team 成员描述覆盖。 */
async function handleSaveTeamMember(member: AgentTeamMemberConfigItem) {
  const draft = teamMemberDrafts[member.id]
  if (draft === undefined) return
  savingTeamMemberId.value = member.id
  try {
    const normalizedDescription = draft.trim()
    await updateAgentConfig(member.id, {
      description_override: normalizedDescription && normalizedDescription !== member.default_description
        ? normalizedDescription
        : null,
    })
    await refreshAgentQueries()
    Message.success('成员描述已保存。')
  } catch (error) {
    Message.error(getErrorMessage(error, '保存成员描述失败。'))
  } finally {
    savingTeamMemberId.value = null
  }
}

/** 恢复 Team 成员默认描述。 */
async function handleRestoreTeamMember(member: AgentTeamMemberConfigItem) {
  savingTeamMemberId.value = member.id
  try {
    await updateAgentConfig(member.id, {
      description_override: null,
    })
    await refreshAgentQueries()
    Message.success('成员描述已恢复默认。')
  } catch (error) {
    Message.error(getErrorMessage(error, '恢复成员描述失败。'))
  } finally {
    savingTeamMemberId.value = null
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

/** 批量切换工具组内所有可配置工具。 */
async function handleSetGroupEnabled(group: AgentToolGroupConfigItem, enabled: boolean) {
  if (!selectedAgentConfig.value) return
  savingGroupKey.value = group.key
  try {
    for (const tool of group.tools.filter(item => item.configurable)) {
      const draft = toolDrafts[tool.key]
      await updateAgentToolConfig(selectedAgentConfig.value.id, tool.key, {
        enabled,
        description_override: draft?.descriptionOverride.trim() || tool.description_override,
        instructions_override: draft?.instructionsOverride.trim() || tool.instructions_override,
      })
    }
    await refreshAgentQueries()
    Message.success(enabled ? '工具组已开启。' : '工具组已关闭。')
  } catch (error) {
    Message.error(getErrorMessage(error, '批量更新工具组失败。'))
  } finally {
    savingGroupKey.value = null
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

/** 判断 Team 成员描述草稿是否发生变化。 */
function isTeamMemberDirty(member: AgentTeamMemberConfigItem) {
  return (teamMemberDrafts[member.id] ?? '').trim() !== member.description
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

/** 重置模型表单并切换到新建状态。 */
function resetModelForm() {
  activeSection.value = 'models'
  selectedConfigId.value = null
  modelForm.scope = 'personal'
  modelForm.name = ''
  const provider = providersQuery.data.value?.length
    ? findDefaultNewModelProvider(providersQuery.data.value)
    : null
  modelForm.provider_key = provider?.provider_key ?? null
  prefillModelFormFromProvider(provider)
  modelForm.api_key = ''
  modelForm.history_token_ratio = 0.5
  modelForm.compression_target_ratio = DEFAULT_COMPRESSION_TARGET_RATIO
  advancedConfigText.value = '{}'
  advancedConfigError.value = ''
  advancedConfigCollapsed.value = true
}

/** 把已有模型装载到右侧表单。 */
async function handleEditModel(config: LlmConfigItem) {
  activeSection.value = 'models'
  applyingExistingModel.value = true
  selectedConfigId.value = config.id
  modelForm.scope = config.scope
  modelForm.name = config.name
  modelForm.provider_key = config.provider_key
  modelForm.model_id = config.model_id
  modelForm.base_url = config.base_url ?? ''
  modelForm.api_key = ''
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

/** 创建或更新模型。 */
async function handleSubmitModel() {
  if (selectedModel.value && !selectedModel.value.editable) {
    Message.error('管理员全局模型只读，不能由当前用户修改。')
    return
  }
  const providerKey = modelForm.provider_key
  if (!modelForm.name.trim() || !providerKey || !modelForm.model_id.trim()) {
    Message.error('请先填写模型名称、供应商和模型 ID。')
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
        provider_key: providerKey,
        model_id: modelForm.model_id.trim(),
        base_url: modelForm.base_url.trim() || null,
        thinking_enabled: modelForm.thinking_enabled,
        thinking_effort: modelForm.thinking_effort,
        supports_image_input: modelForm.supports_image_input,
        context_window_tokens: normalizePositiveInteger(modelForm.context_window_tokens, DEFAULT_CONTEXT_WINDOW_TOKENS),
        max_output_tokens: normalizePositiveInteger(modelForm.max_output_tokens, DEFAULT_MAX_OUTPUT_TOKENS),
        history_token_ratio: normalizeHistoryRatio(modelForm.history_token_ratio),
        compression_target_ratio: normalizeCompressionTargetRatio(modelForm.compression_target_ratio),
        advanced_config_json: advancedConfig,
      }
      const nextApiKey = modelForm.api_key.trim()
      if (nextApiKey) {
        updatePayload.api_key = nextApiKey
      }
      await updateLlmConfig(selectedConfigId.value, updatePayload)
      Message.success('模型已更新。')
    } else {
      await createLlmConfig({
        name: modelForm.name.trim(),
        scope: modelForm.scope,
        provider_key: providerKey,
        model_id: modelForm.model_id.trim(),
        base_url: modelForm.base_url.trim() || null,
        api_key: modelForm.api_key.trim() || null,
        thinking_enabled: modelForm.thinking_enabled,
        thinking_effort: modelForm.thinking_effort,
        supports_image_input: modelForm.supports_image_input,
        context_window_tokens: normalizePositiveInteger(modelForm.context_window_tokens, DEFAULT_CONTEXT_WINDOW_TOKENS),
        max_output_tokens: normalizePositiveInteger(modelForm.max_output_tokens, DEFAULT_MAX_OUTPUT_TOKENS),
        history_token_ratio: normalizeHistoryRatio(modelForm.history_token_ratio),
        compression_target_ratio: normalizeCompressionTargetRatio(modelForm.compression_target_ratio),
        advanced_config_json: advancedConfig,
      })
      Message.success('模型已创建。')
      resetModelForm()
    }
    await refreshLlmQueries()
  } catch (error) {
    Message.error(getErrorMessage(error, '保存模型失败。'))
  } finally {
    savingConfig.value = false
  }
}

/** 切换模型启用状态。 */
async function handleToggleModelStatus(config: LlmConfigItem) {
  statusUpdatingConfigId.value = config.id
  try {
    await updateLlmConfig(config.id, {
      status: config.status === 'active' ? 'archived' : 'active',
    })
    Message.success(config.status === 'active' ? '模型已归档。' : '模型已恢复。')
    await refreshLlmQueries()
  } catch (error) {
    Message.error(getErrorMessage(error, '更新模型状态失败。'))
  } finally {
    statusUpdatingConfigId.value = null
  }
}

/** 刷新模型、模型绑定与运行入口相关缓存。 */
async function refreshLlmQueries() {
  await Promise.all([
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

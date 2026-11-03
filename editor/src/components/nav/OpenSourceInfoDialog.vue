<!-- 文件功能：开源与许可弹窗，说明项目自身的双许可范围，并以标签页按作用分组展示平台直接依赖的开源项目。 -->
<template>
  <UiDialog
    :open="open"
    title="开源与许可"
    size="standard"
    body-preset="auto"
    :panel-style="{ height: 'auto' }"
    @update:open="emit('update:open', $event)"
  >
    <div class="space-y-5">
      <section>
        <h3 class="text-sm font-black text-text-strong">本项目许可</h3>
        <div class="mt-2.5 grid gap-2 sm:grid-cols-2">
          <a
            v-for="entry in PROJECT_LICENSES"
            :key="entry.key"
            :href="entry.href"
            target="_blank"
            rel="noreferrer"
            class="flex min-w-0 items-center justify-between gap-2 rounded-xl border border-border bg-surface px-3.5 py-2.5 transition-colors hover:border-border-strong hover:bg-surface-muted"
          >
            <span class="truncate text-sm font-bold text-text-strong">{{ entry.title }}</span>
            <span class="shrink-0 rounded border border-border bg-canvas px-1.5 py-0.5 text-[10px] font-semibold text-text-muted">
              {{ entry.license }}
            </span>
          </a>
        </div>
      </section>

      <section>
        <h3 class="text-sm font-black text-text-strong">开源依赖</h3>
        <UiTabs
          v-model="activeGroup"
          class="mt-2.5"
          :items="tabItems"
          list-class="overflow-x-auto"
          content-class="pt-3"
        >
          <template #panel="{ item }">
            <ul class="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
              <li
                v-for="dep in groupItems(item.value)"
                :key="dep.name"
                class="flex min-h-6 min-w-0 items-center justify-between gap-2 border-b border-border-muted/60 pb-1.5"
              >
                <span class="flex min-w-0 items-center gap-1">
                  <a
                    v-if="dep.href"
                    :href="dep.href"
                    target="_blank"
                    rel="noreferrer"
                    class="truncate text-xs font-semibold text-text underline-offset-2 hover:underline"
                  >
                    {{ dep.name }}
                  </a>
                  <span v-else class="truncate text-xs font-semibold text-text">{{ dep.name }}</span>
                  <UiTooltip v-if="dep.note">
                    <template #trigger>
                      <UiIconButton
                        size="xs"
                        :label="`${dep.name} 许可说明`"
                      >
                        <Info aria-hidden="true" />
                      </UiIconButton>
                    </template>
                    <span class="block max-w-[240px] leading-5">{{ dep.note }}</span>
                  </UiTooltip>
                </span>
                <span class="shrink-0 rounded border border-border bg-surface px-1.5 py-0.5 text-[10px] font-medium text-text-muted">
                  {{ dep.license }}
                </span>
              </li>
            </ul>
          </template>
        </UiTabs>
      </section>
    </div>

    <template #footer>
      <a
        :href="REPO_HOME_URL"
        target="_blank"
        rel="noreferrer"
        class="mr-auto inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-semibold text-text-secondary transition-colors hover:bg-surface-muted hover:text-text"
      >
        在 GitHub 查看
        <ExternalLink class="h-3 w-3 text-text-disabled" aria-hidden="true" />
      </a>
      <UiButton variant="ghost" @click="emit('update:open', false)">关闭</UiButton>
    </template>
  </UiDialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ExternalLink, Info } from '@lucide/vue'

import { UiButton, UiDialog, UiIconButton, UiTabs, UiTooltip } from '@/components/ui'
import { OPEN_SOURCE_GROUPS, PROJECT_LICENSES } from './open-source-notices'
import { REPO_HOME_URL } from '@/utils/repo-links'

defineProps<{
  /** 弹窗是否可见，由调用方受控。 */
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const activeGroup = ref(OPEN_SOURCE_GROUPS[0]?.key ?? '')
const tabItems = computed(() => OPEN_SOURCE_GROUPS.map(group => ({ label: group.title, value: group.key })))

/**
 * 按标签页 value 取出对应分组的依赖条目。
 * @param key 分组标识，与标签页 value 一致
 * @returns 该分组的条目列表；未命中时返回空列表
 */
function groupItems(key: string) {
  return OPEN_SOURCE_GROUPS.find(group => group.key === key)?.items ?? []
}
</script>

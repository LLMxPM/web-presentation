<!-- 文件功能：提供工作空间右侧统一 Dock，承载完整页面导航与底部素材/组件抽屉入口。 -->
<template>
  <aside
    data-testid="workspace-dock"
    class="flex h-full w-14 shrink-0 flex-col items-center border-l border-border bg-surface px-1 py-3 shadow-sm"
  >
    <div class="flex min-h-0 flex-1 flex-col items-center gap-1.5">
      <UiButton
        v-for="item in navigationItems"
        :key="item.key"
        variant="ghost"
        :data-testid="`workspace-dock-${item.key}`"
        :title="item.title"
        :aria-label="item.title"
        class="dock-button [&>span]:flex-col [&>span]:gap-0"
        :class="item.key === activeKey ? 'dock-button-active' : 'dock-button-idle'"
        @click="emit('navigate', item.path)"
      >
        <component :is="item.icon" class="h-5 w-5" />
        <span class="mt-1 text-[10px] font-bold leading-none">{{ item.label }}</span>
      </UiButton>
    </div>

    <div class="mt-auto flex flex-col items-center pt-1.5">
      <UiIconButton
        v-if="drawerClosed"
        variant="primary"
        size="md"
        class="library-drawer-trigger !h-10 !w-10 !rounded-full shadow-popover"
        data-dialog-overlay-trigger
        label="打开素材 / 组件侧栏"
        title="打开素材 / 组件侧栏（Ctrl+Shift+K）"
        @click="toggleLibraryDrawer"
      >
        <Library class="h-5 w-5" />
      </UiIconButton>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Image, Layers, LayoutDashboard, Library, Palette, SwatchBook } from '@lucide/vue'

import { useLibraryDrawerState } from '@/composables/library-drawer-state'
import { UiButton, UiIconButton } from '@/components/ui'
import {
  buildWorkspaceAssetsPath,
  buildWorkspaceComponentsPath,
  buildWorkspaceHomePath,
  buildWorkspaceStylesPath,
  buildWorkspaceThemesPath,
  type WorkspaceRouteKey,
} from '@/utils/workspace-routes'

const props = defineProps<{
  workspaceId: number
  activeKey: WorkspaceRouteKey
}>()

const emit = defineEmits<{
  navigate: [path: string]
}>()

const { activePanel, openLibraryDrawer, closeLibraryDrawer } = useLibraryDrawerState()
const drawerClosed = computed(() => activePanel.value === null)

/**
 * 抽屉关闭时打开素材页签，打开时收起抽屉。
 */
function toggleLibraryDrawer(): void {
  if (activePanel.value === null) {
    openLibraryDrawer('assets')
    return
  }
  closeLibraryDrawer()
}

/**
 * 生成完整页面导航项，点击后主内容区进行路由切换。
 */
const navigationItems = computed(() => [
  {
    key: 'projects' as const,
    label: '项目',
    title: '项目与页面',
    icon: LayoutDashboard,
    path: buildWorkspaceHomePath(props.workspaceId),
  },
  {
    key: 'components' as const,
    label: '组件',
    title: '组件库',
    icon: Layers,
    path: buildWorkspaceComponentsPath(props.workspaceId),
  },
  {
    key: 'assets' as const,
    label: '资源',
    title: '资源库',
    icon: Image,
    path: buildWorkspaceAssetsPath(props.workspaceId),
  },
  {
    key: 'themes' as const,
    label: '主题',
    title: '主题与字体',
    icon: SwatchBook,
    path: buildWorkspaceThemesPath(props.workspaceId),
  },
  {
    key: 'styles' as const,
    label: '样式',
    title: '样式库',
    icon: Palette,
    path: buildWorkspaceStylesPath(props.workspaceId),
  },
])
</script>

<style scoped>
.dock-button {
  position: relative;
  display: inline-flex;
  min-height: 52px;
  width: 48px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  border: 1px solid transparent;
  transition: all 0.18s ease;
}

.dock-button-idle {
  color: rgb(var(--ui-text-muted));
}

.dock-button-idle:hover {
  border-color: rgb(var(--ui-border));
  background: rgb(var(--ui-surface-hover));
  color: rgb(var(--ui-text));
}

.dock-button-active {
  border-color: rgb(var(--ui-accent-ring));
  background: rgb(var(--ui-surface-selected));
  color: rgb(var(--ui-accent));
  box-shadow: 0 1px 2px rgb(var(--ui-accent) / 0.12);
}

/*
 * 普通 UiDialog 会在 body 上禁用指针事件；抽屉入口需要显式恢复交互，
 * 并使用统一 Token 越过普通弹窗，确保用户可从任意工作流打开素材抽屉。
 */
.library-drawer-trigger {
  z-index: var(--ui-z-drawer-trigger);
  pointer-events: auto;
}
</style>

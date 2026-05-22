<!-- 文件功能：提供工作空间右侧统一 Dock，承载完整页面导航与轻量辅助面板开关。 -->
<template>
  <aside
    data-testid="workspace-dock"
    class="flex h-full w-14 shrink-0 flex-col items-center border-l border-slate-200 bg-white px-1 py-3 shadow-sm"
  >
    <div class="flex min-h-0 flex-1 flex-col items-center gap-1.5">
      <button
        v-for="item in navigationItems"
        :key="item.key"
        type="button"
        :data-testid="`workspace-dock-${item.key}`"
        :title="item.title"
        :aria-label="item.title"
        class="dock-button"
        :class="item.key === activeKey ? 'dock-button-active' : 'dock-button-idle'"
        @click="emit('navigate', item.path)"
      >
        <component :is="item.icon" class="h-5 w-5" />
        <span class="mt-1 text-[10px] font-bold leading-none">{{ item.label }}</span>
      </button>

      <div class="mt-2 h-px w-8 bg-slate-200" />
      <span class="text-[10px] font-bold leading-none text-slate-300" aria-hidden="true">侧栏</span>

      <button
        v-for="item in panelItems"
        :key="item.key"
        type="button"
        :data-testid="`workspace-dock-panel-${item.key}`"
        :title="item.title"
        :aria-label="item.title"
        class="dock-button"
        :class="item.key === activePanel ? 'dock-button-panel-active' : 'dock-button-idle'"
        @click="emit('toggle-panel', item.key)"
      >
        <component :is="item.icon" class="h-5 w-5" />
        <span class="mt-1 text-[10px] font-bold leading-none">{{ item.label }}</span>
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Image, Layers, LayoutDashboard, Palette, SwatchBook } from 'lucide-vue-next'

import {
  buildWorkspaceAssetsPath,
  buildWorkspaceComponentsPath,
  buildWorkspaceHomePath,
  buildWorkspaceStylesPath,
  buildWorkspaceThemesPath,
  type WorkspaceRouteKey,
} from '@/utils/workspace-routes'

type WorkspaceDockPanelKey = 'assets' | 'components' | 'themes'

const props = defineProps<{
  workspaceId: number
  activeKey: WorkspaceRouteKey
  activePanel: WorkspaceDockPanelKey | null
}>()

const emit = defineEmits<{
  navigate: [path: string]
  'toggle-panel': [panel: WorkspaceDockPanelKey]
}>()

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

/**
 * 生成轻量辅助面板项，点击后从 Dock 左侧展开侧栏。
 */
const panelItems = [
  {
    key: 'assets' as const,
    label: '素材',
    title: '资源库侧栏',
    icon: Image,
  },
  {
    key: 'components' as const,
    label: '组件',
    title: '组件库侧栏',
    icon: Layers,
  },
  {
    key: 'themes' as const,
    label: '字体',
    title: '打开侧栏：主题字体速览',
    icon: SwatchBook,
  },
]
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
  color: rgb(100 116 139);
}

.dock-button-idle:hover {
  border-color: rgb(226 232 240);
  background: rgb(248 250 252);
  color: rgb(30 41 59);
}

.dock-button-active {
  border-color: rgb(199 210 254);
  background: rgb(238 242 255);
  color: rgb(79 70 229);
  box-shadow: 0 1px 2px rgb(79 70 229 / 0.12);
}

.dock-button-panel-active {
  border-color: rgb(167 243 208);
  background: rgb(236 253 245);
  color: rgb(4 120 87);
  box-shadow: 0 1px 2px rgb(4 120 87 / 0.12);
}
</style>

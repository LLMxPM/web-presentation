<!--
  文件用途：本地能力总览页，按 manifest 实时汇总公开能力、章节入口和演示路由，避免示例与契约漂移。
-->
<template>
  <ShowcasePage title="Runtime 能力总览" subtitle="按 manifest 汇总的全部公开能力，以及对应的本地演示页面" :capabilities="[]">
    <div class="grid h-full min-h-0 grid-cols-[0.92fr_1.08fr] gap-5">
      <section class="flex min-h-0 flex-col gap-4">
        <div class="rounded-lg border border-border-subtle bg-background-subtle p-5">
          <div class="flex items-center gap-2">
            <Icon name="star" class="size-5 text-primary" />
            <h2 class="font-heading text-lg font-semibold text-primary">Runtime Kit 只公开运行时能力</h2>
          </div>
          <p class="mt-3 font-body text-sm leading-7 text-secondary">
            资源解析、特殊格式渲染、页面与路由上下文、主题与图标、DOM 连线这类必须依赖浏览器 Runtime
            上下文的能力才会进入公开清单；卡片、栅格、页头页脚等视觉结构由页面源码自行生成。
          </p>
          <div class="mt-4 grid grid-cols-3 gap-3">
            <div v-for="stat in stats" :key="stat.label" class="rounded-md bg-default px-3 py-2">
              <p class="font-heading text-2xl font-semibold text-primary">{{ stat.value }}</p>
              <p class="font-body text-xs text-secondary">{{ stat.label }}</p>
            </div>
          </div>
        </div>

        <div class="grid min-h-0 flex-1 grid-cols-1 gap-3">
          <article
            v-for="chapter in chapters"
            :key="chapter.route"
            class="flex flex-col justify-center gap-2 rounded-lg border border-border-subtle bg-default p-4"
          >
            <div class="flex items-center gap-3">
              <span class="flex size-10 shrink-0 items-center justify-center rounded-md" :class="chapter.iconClass">
                <Icon :name="chapter.icon" class="size-5" />
              </span>
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2">
                  <h3 class="font-heading text-base font-semibold text-primary">{{ chapter.title }}</h3>
                  <span class="rounded-full px-2 py-0.5 font-body text-xs font-medium" :class="chapter.badgeClass">
                    {{ chapter.pages.length }} 页
                  </span>
                </div>
                <p class="mt-0.5 truncate font-body text-xs text-secondary">{{ chapter.description }}</p>
              </div>
              <router-link
                :to="chapter.route"
                class="shrink-0 font-body text-sm text-link transition-colors hover:text-link-hover"
              >
                进入 →
              </router-link>
            </div>
            <div class="flex flex-wrap gap-1.5 pl-12">
              <router-link
                v-for="item in chapter.pages"
                :key="item.route"
                :to="item.route"
                class="rounded-full border border-border-subtle bg-background-subtle px-2.5 py-1 font-body text-xs text-secondary transition-colors hover:border-primary-300 hover:text-primary"
              >
                {{ item.label }}
              </router-link>
            </div>
          </article>
        </div>
      </section>

      <section class="flex min-h-0 flex-col rounded-lg border border-border bg-background-subtle p-5">
        <div class="mb-3 flex items-end justify-between gap-4">
          <div>
            <h2 class="font-heading text-lg font-semibold text-primary">公开能力矩阵</h2>
            <p class="mt-1 font-body text-xs text-secondary">
              直接读取 runtime-kit.manifest.json；点击能力名进入对应演示页
            </p>
          </div>
          <div class="flex items-center gap-3 font-body text-xs text-secondary">
            <span class="flex items-center gap-1"><span class="size-2 rounded-full bg-accent2" /> 组件</span>
            <span class="flex items-center gap-1"><span class="size-2 rounded-full bg-accent1" /> 组合式</span>
            <span class="flex items-center gap-1"><span class="size-2 rounded-full bg-accent4" /> 工具函数</span>
          </div>
        </div>

        <div class="grid min-h-0 flex-1 grid-cols-3 gap-3">
          <div v-for="group in matrix" :key="group.category" class="flex min-h-0 flex-col rounded-md border border-border-subtle bg-default p-3">
            <div class="mb-2 flex items-center justify-between">
              <h3 class="font-heading text-sm font-semibold text-primary">{{ group.label }}</h3>
              <span class="font-code text-xs text-secondary">{{ group.items.length }}</span>
            </div>
            <ul class="min-h-0 flex-1 space-y-1 overflow-auto">
              <li v-for="item in group.items" :key="item.name">
                <router-link
                  v-if="item.route"
                  :to="item.route"
                  class="flex items-center gap-2 rounded px-2 py-1.5 transition-colors hover:bg-background-subtle"
                >
                  <span class="size-1.5 shrink-0 rounded-full" :class="kindDotClass(item.kind)" />
                  <span class="min-w-0 flex-1 truncate font-body text-xs text-primary">{{ item.label }}</span>
                  <span class="font-code text-xs text-secondary">{{ item.name }}</span>
                </router-link>
                <div v-else class="flex items-center gap-2 rounded px-2 py-1.5">
                  <span class="size-1.5 shrink-0 rounded-full" :class="kindDotClass(item.kind)" />
                  <span class="min-w-0 flex-1 truncate font-body text-xs text-secondary">{{ item.label }}</span>
                  <span class="rounded bg-background-subtle px-1.5 py-0.5 font-body text-xs text-secondary">契约</span>
                </div>
              </li>
            </ul>
          </div>
        </div>
      </section>
    </div>
  </ShowcasePage>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ShowcasePage from '@/examples/local/components/ShowcasePage.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'
import manifest from '@/runtime-kit/manifest/runtime-kit.manifest.json'

/** manifest 中单条导出记录；只取演示页需要的字段。 */
interface ManifestExport {
  name: string
  kind: 'component' | 'composable' | 'util' | string
  category: 'asset' | 'page' | 'runtime' | string
  import_path: string
  capability?: {
    display_name?: string
    summary?: string
    recommendation_level?: string
  }
}

/** 能力名与演示路由的映射；没有路由的能力只展示契约。 */
const demoRoutes: Record<string, string> = {
  'DefaultContainer.v1': '/page-runtime/canvas',
  'usePageSize.v1': '/page-runtime/canvas',
  'buildPageCanvasStyle.v1': '/page-runtime/canvas',
  'useCurrentPage.v1': '/page-runtime/routing',
  'useRouteCatalog.v1': '/page-runtime/routing',
  'usePageNavigation.v1': '/page-runtime/routing',
  'useTheme.v1': '/runtime-kit/theme',
  'resolveColor.v1': '/runtime-kit/theme',
  'Icon.v1': '/runtime-kit/icons',
  'ThemeLogo.v1': '/runtime-kit/icons',
  'DataTable.v1': '/runtime-kit/data-table',
  'Connector.v1': '/runtime-kit/connector',
  'usePageScene.v1': '/runtime-kit/scene',
  'useStaticPresentation.v1': '/runtime-kit/scene',
  'createSceneMediaTask.v1': '/runtime-kit/scene',
  'AssetImage.v1': '/assets/image',
  'useAssetSrc.v1': '/assets/image',
  'useAssetBackground.v1': '/assets/image',
  'resolveResourcePath.v1': '/assets/image',
  'AssetVideo.v1': '/assets/video',
  'AssetAudio.v1': '/assets/audio',
  'useAudioCue.v1': '/assets/audio',
  'AssetChart.v1': '/assets/chart',
  'AssetMermaid.v1': '/assets/mermaid',
  'AssetDrawio.v1': '/assets/drawio',
  'AssetFormula.v1': '/assets/formula',
  'AssetModel.v1': '/assets/model',
}

const manifestExports = manifest.exports as ManifestExport[]

const categoryLabels: Record<string, string> = {
  asset: '资源渲染 asset',
  page: '页面与路由 page',
  runtime: '运行时能力 runtime',
}

/**
 * 汇总指标：公开能力总数、示例页数量和章节数量。
 */
const stats = computed(() => [
  { label: '公开能力', value: manifestExports.length },
  { label: '示例页', value: chapters.reduce((total, chapter) => total + chapter.pages.length, 0) + 1 },
  { label: '能力章节', value: chapters.length },
])

/** 三个章节入口，与路由配置中的分组保持一一对应。 */
const chapters = [
  {
    title: '资源渲染',
    route: '/assets/image',
    description: '图片、视频、音频、图表、Mermaid、Drawio、公式与三维模型',
    icon: '扫描',
    iconClass: 'bg-accent1-100 text-accent1-700',
    badgeClass: 'bg-accent1-100 text-accent1-800',
    pages: [
      { label: '图片与资源解析', route: '/assets/image' },
      { label: '视频渲染', route: '/assets/video' },
      { label: '音频与音效', route: '/assets/audio' },
      { label: 'ECharts 图表', route: '/assets/chart' },
      { label: 'Mermaid 图表', route: '/assets/mermaid' },
      { label: 'Draw.io 图表', route: '/assets/drawio' },
      { label: 'LaTeX 公式', route: '/assets/formula' },
      { label: '三维模型', route: '/assets/model' },
    ],
  },
  {
    title: '页面与路由',
    route: '/page-runtime/canvas',
    description: '固定画布尺寸、标准画布样式与两级路由上下文',
    icon: '缩小',
    iconClass: 'bg-accent2-100 text-accent2-700',
    badgeClass: 'bg-accent2-100 text-accent2-800',
    pages: [
      { label: '页面画布', route: '/page-runtime/canvas' },
      { label: '路由与导航', route: '/page-runtime/routing' },
    ],
  },
  {
    title: '运行时能力',
    route: '/runtime-kit/theme',
    description: '主题、图标与 Logo、表格、DOM 连线与场景动画',
    icon: 'slider',
    iconClass: 'bg-accent3-100 text-accent3-700',
    badgeClass: 'bg-accent3-100 text-accent3-800',
    pages: [
      { label: '主题与配色', route: '/runtime-kit/theme' },
      { label: '图标与 Logo', route: '/runtime-kit/icons' },
      { label: 'DataTable 表格', route: '/runtime-kit/data-table' },
      { label: 'DOM 连线', route: '/runtime-kit/connector' },
      { label: '场景与动效', route: '/runtime-kit/scene' },
    ],
  },
]

/**
 * 按 category 分列的公开能力矩阵。
 */
const matrix = computed(() => ['asset', 'page', 'runtime'].map((category) => ({
  category,
  label: categoryLabels[category],
  items: manifestExports
    .filter((item) => item.category === category)
    .map((item) => ({
      name: item.name,
      kind: item.kind,
      label: item.capability?.display_name || item.name,
      route: demoRoutes[item.name] || '',
    }))
    .sort((left, right) => left.label.localeCompare(right.label, 'zh-CN')),
})))

/**
 * 能力类型对应的颜色圆点。
 * @param kind manifest 中的 kind
 * @returns Tailwind 背景类
 */
function kindDotClass(kind: string): string {
  if (kind === 'component') return 'bg-accent2'
  if (kind === 'composable') return 'bg-accent1'
  return 'bg-accent4'
}
</script>

<!--
  文件用途：本地三维示例页，用公开 GLB 演示 AssetModel 的取景、背景与交互参数。
  约束：本地 fixture 没有资源清单，直接以 URL 驱动内部 ModelViewer；平台页面使用 AssetModel + 资源名。
-->
<template>
  <ShowcasePage
    title="三维模型"
    subtitle="公开示例 GLB 演示自动取景、显式相机与交互查看"
    :capabilities="capabilities"
  >
    <div class="grid h-full min-h-0 grid-cols-5 gap-5">
      <section class="col-span-3 flex min-h-0 flex-col rounded-lg border border-border-subtle bg-background-subtle p-4">
        <div class="mb-3 flex items-center gap-2">
          <Icon name="扫描" class="size-5 text-primary" />
          <h2 class="font-heading text-lg font-semibold text-primary">{{ currentModel.label }}</h2>
          <span class="rounded-full bg-background px-2 py-0.5 font-code text-xs text-secondary">{{ currentModel.file }}</span>
          <span class="ml-auto font-body text-xs text-secondary">{{ currentModel.license }}</span>
        </div>

        <div class="flex min-h-0 flex-1 items-center justify-center rounded-md border border-border bg-default p-2">
          <ModelViewer
            :key="viewerKey"
            :name="currentModel.key"
            :src="currentModel.url"
            :interactive="interactive"
            :camera-position="explicitCamera?.position"
            :camera-target="explicitCamera?.target"
            :background="background"
            :lighting="lighting"
            fallback="模型加载失败，请检查 public/model 下的示例文件。"
            class="h-full w-full rounded-md"
          />
        </div>

        <div class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 font-body text-xs text-secondary">
          <span>{{ currentModel.summary }}</span>
          <span class="font-code">{{ currentModel.size }}</span>
          <span class="font-code">meshes {{ currentModel.meshes }}</span>
          <span class="font-code">materials {{ currentModel.materials }}</span>
          <span class="font-code">animations {{ currentModel.animations }}</span>
          <span class="ml-auto">{{ framingLabel }}</span>
        </div>
      </section>

      <section class="col-span-2 flex min-h-0 flex-col gap-4">
        <div class="rounded-lg border border-border bg-background-subtle p-4">
          <div class="mb-3 flex items-center gap-2">
            <Icon name="slider" class="size-4 text-primary" />
            <h3 class="font-heading text-base font-semibold text-primary">渲染参数</h3>
            <button
              type="button"
              class="ml-auto rounded-md border border-border px-2.5 py-1 font-body text-xs text-primary transition-colors hover:border-primary-300"
              @click="resetView"
            >
              重置视角
            </button>
          </div>

          <label class="mb-3 block space-y-1.5">
            <span class="font-body text-xs text-secondary">取景方式 framing</span>
            <select v-model="framing" class="showcase-input">
              <option value="auto">auto · 自动取景</option>
              <option value="explicit">explicit · 3/4 显式相机</option>
            </select>
          </label>

          <div class="grid grid-cols-2 gap-3">
            <label class="space-y-1.5">
              <span class="font-body text-xs text-secondary">背景 background</span>
              <select v-model="background" class="showcase-input">
                <option value="transparent">transparent</option>
                <option value="#0f172a">#0f172a</option>
                <option value="#f4f4f4">#f4f4f4</option>
                <option value="#20364d">#20364d</option>
              </select>
            </label>
            <label class="space-y-1.5">
              <span class="font-body text-xs text-secondary">光照 lighting</span>
              <select v-model="lighting" class="showcase-input">
                <option value="auto">auto · 缺光时补默认</option>
                <option value="source">source · 只用源文件</option>
              </select>
            </label>
          </div>

          <label class="mt-3 flex items-center gap-2.5">
            <input v-model="interactive" type="checkbox" class="size-4 accent-primary" />
            <span class="font-body text-xs text-primary">开启交互查看 interactive</span>
          </label>
          <p class="mt-2 font-body text-xs leading-6 text-secondary">
            开启 interactive 后只做查看交互，不再发放动画句柄；静态渲染不播放模型自带动画。
          </p>
        </div>

        <div class="flex min-h-0 flex-1 flex-col rounded-lg border border-border bg-background-subtle p-4">
          <div class="mb-2 flex items-center justify-between">
            <h3 class="font-heading text-base font-semibold text-primary">模型清单</h3>
            <span class="font-body text-xs text-secondary">公开资源 · 见 ATTRIBUTION.md</span>
          </div>
          <ul class="min-h-0 flex-1 space-y-1 overflow-auto">
            <li v-for="model in models" :key="model.key">
              <button
                type="button"
                class="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left transition-colors"
                :class="model.key === currentModel.key ? 'bg-primary-50' : 'hover:bg-background'"
                @click="selectModel(model.key)"
              >
                <span class="size-1.5 shrink-0 rounded-full" :class="model.key === currentModel.key ? 'bg-primary' : 'bg-border'" />
                <span class="min-w-0 flex-1 truncate font-body text-xs text-primary">{{ model.label }}</span>
                <span class="shrink-0 font-code text-xs text-secondary">{{ model.size }}</span>
                <span class="w-20 shrink-0 text-right font-code text-xs text-secondary">{{ model.licenseShort }}</span>
              </button>
            </li>
          </ul>
          <p class="mt-2 border-t border-border-subtle pt-2 font-body text-xs leading-6 text-secondary">
            平台页面使用 AssetModel：
            <code class="font-code text-primary">name</code> 引用 manifest 登记的 GLB，
            <code class="font-code text-primary">camera-position</code> /
            <code class="font-code text-primary">camera-target</code> 显式取景。
          </p>
        </div>
      </section>
    </div>
  </ShowcasePage>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import ShowcasePage, { type ShowcaseCapability } from '@/examples/local/components/ShowcasePage.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'
import ModelViewer from '@runtime-kit/internal/renderers/ModelViewer.vue'

type ModelKey = 'box' | 'box-animated' | 'rigged-figure' | 'fox' | 'robot-expressive'

interface ShowcaseModel {
  /** 模型标识，同时作为 viewer 的资源名 */
  key: ModelKey
  /** 展示名称 */
  label: string
  /** 文件名 */
  file: string
  /** 一句话特点 */
  summary: string
  /** 文件体积展示 */
  size: string
  /** 授权短标签 */
  licenseShort: string
  /** 完整授权说明 */
  license: string
  /** 网格数量 */
  meshes: number
  /** 材质数量 */
  materials: number
  /** 动画片段数量 */
  animations: number
  /** 可访问地址 */
  url: string
  /** 显式取景参数：相机位置与目标点 */
  camera: { position: [number, number, number]; target: [number, number, number] }
}

const capabilities: ShowcaseCapability[] = [
  { name: 'AssetModel.v1', path: '@runtime-kit/public/components/assets/AssetModel.v1.vue' },
  { name: 'ModelViewer', path: 'internal/renderers/ModelViewer.vue', local: true },
]

/** 本地示例模型；元数据由 GLB 头部解析得出，授权见 public/model/ATTRIBUTION.md。 */
const models: ShowcaseModel[] = [
  {
    key: 'box',
    label: 'Box · 基础几何',
    file: 'box.glb',
    summary: '单网格单材质，用来验证取景基准',
    size: '1.6 KB',
    licenseShort: 'CC BY 4.0',
    license: 'Cesium · CC BY 4.0',
    meshes: 1,
    materials: 1,
    animations: 0,
    camera: {
      position: [0.954, 0.591, 2.272],
      target: [0, 0, 0],
    },
    url: `${import.meta.env.BASE_URL}model/box.glb`,
  },
  {
    key: 'box-animated',
    label: 'Box Animated · 双通道动画',
    file: 'box-animated.glb',
    summary: '旋转与位移两条通道，静态渲染停在默认姿态',
    size: '12 KB',
    licenseShort: 'CC BY 4.0',
    license: 'Cesium · CC BY 4.0',
    meshes: 2,
    materials: 2,
    animations: 1,
    camera: {
      position: [0.954, 0.591, 2.272],
      target: [0, 0, 0],
    },
    url: `${import.meta.env.BASE_URL}model/box-animated.glb`,
  },
  {
    key: 'rigged-figure',
    label: 'Rigged Figure · 骨骼蒙皮',
    file: 'rigged-figure.glb',
    summary: '单骨骼蒙皮网格，验证 skin 与关节层级加载',
    size: '49 KB',
    licenseShort: 'CC BY 4.0',
    license: 'Cesium · CC BY 4.0',
    meshes: 1,
    materials: 1,
    animations: 1,
    camera: {
      position: [1.08, 1.28, 2.59],
      target: [0, 0.608, 0.021],
    },
    url: `${import.meta.env.BASE_URL}model/rigged-figure.glb`,
  },
  {
    key: 'fox',
    label: 'Fox · 三段动作',
    file: 'fox.glb',
    summary: 'Survey / Walk / Run 三段循环动作，静态只取默认姿态',
    size: '159 KB',
    licenseShort: 'CC0 + BY',
    license: 'PixelMannen CC0 · 绑定与转换 CC BY 4.0',
    meshes: 1,
    materials: 1,
    animations: 3,
    camera: {
      position: [66.55, 71.56, 142.875],
      target: [0.001, 30.363, -15.574],
    },
    url: `${import.meta.env.BASE_URL}model/fox.glb`,
  },
  {
    key: 'robot-expressive',
    label: 'Robot Expressive · 多材质多动作',
    file: 'robot-expressive.glb',
    summary: '14 个网格、3 种材质、14 段动作与表情形变',
    size: '453 KB',
    licenseShort: 'CC0',
    license: 'Tomás Laulhé · CC0（Don McCurdy 修改）',
    meshes: 14,
    materials: 3,
    animations: 14,
    camera: {
      position: [3.736, 4.913, 9.027],
      target: [-0.049, 2.57, 0.016],
    },
    url: `${import.meta.env.BASE_URL}model/robot-expressive.glb`,
  },
]

const selectedKey = ref<ModelKey>('robot-expressive')
const framing = ref<'auto' | 'explicit'>('auto')
const interactive = ref(false)
const background = ref('transparent')
const lighting = ref<'auto' | 'source'>('auto')
/** 变更后重建实例，等价于回到自动取景。 */
const resetToken = ref(0)

const currentModel = computed(() => models.find((item) => item.key === selectedKey.value) || models[0])

/** 只有显式取景模式才下发相机参数；自动模式交给 Runtime 按可视包围球取景。 */
const explicitCamera = computed(() => (framing.value === 'explicit' ? currentModel.value.camera : undefined))

const framingLabel = computed(() => {
  if (interactive.value) return '可拖拽旋转 / 滚轮缩放'
  return framing.value === 'explicit' ? '显式相机 · 静态渲染' : '自动取景 · 静态渲染'
})

/** 交互模式与重置次数都参与 key，确保引擎按新参数重新初始化。 */
const viewerKey = computed(() => `${currentModel.value.key}-${framing.value}-${interactive.value ? 'on' : 'off'}-${resetToken.value}`)

/**
 * 切换模型：交互状态保留，视角回到自动取景。
 * @param key 目标模型标识
 */
function selectModel(key: ModelKey): void {
  selectedKey.value = key
  resetToken.value += 1
}

/** 重置当前模型的取景。 */
function resetView(): void {
  resetToken.value += 1
}
</script>

<style scoped>
.showcase-input {
  width: 100%;
  border-radius: 8px;
  border: 1px solid var(--tw-color-border-default);
  background: var(--tw-color-bg-default);
  padding: 8px 10px;
  color: var(--tw-color-text-primary);
  font-size: 13px;
  outline: none;
}
</style>

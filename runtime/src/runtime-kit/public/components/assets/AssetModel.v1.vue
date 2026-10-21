<!--
  文件用途：AssetModel — 基于 manifest 资源名称渲染 Backend 托管的标准 glTF 2.0 / GLB 三维模型。
  传入 name（asset.name）即可，workspaceId、路径解析与 Three.js 引擎加载由内部自动完成。
  name 必须是 manifest 已登记且 render_type=model3d 的逻辑资源名，不接受 URL 或路径。
-->
<template>
  <ModelViewer
    v-if="canRender"
    v-bind="safeAttrs()"
    :data-runtime-asset-name="props.name"
    :name="props.name"
    :src="src"
    :scene-index="props.sceneIndex"
    :camera-index="props.cameraIndex"
    :camera-position="props.cameraPosition"
    :camera-target="props.cameraTarget"
    :camera-fov="props.cameraFov"
    :background="props.background"
    :lighting="props.lighting"
    :interactive="props.interactive"
    :fallback="fallbackMessage"
  />
  <div v-else class="asset-model__fallback" v-bind="safeAttrs()" :data-runtime-asset-name="props.name">{{ fallbackMessage }}</div>
</template>

<script setup lang="ts">
/**
 * AssetModel
 *
 * 使用示例：
 *   <AssetModel name="product" class="w-full h-80" />
 *   <AssetModel name="product" :camera-position="[0, 1, 4]" :camera-target="[0, 0, 0]" />
 *   <AssetModel name="product" :camera-index="1" :interactive="true" />
 *
 * Props:
 *   name           — 资源逻辑名 `asset.name`（必填、稳定资源名；无 src 时显示 fallback）
 *   sceneIndex     — 源文件场景索引；缺省取 glTF 默认场景，仍缺省时取第一个有效场景
 *   cameraIndex    — 源文件相机索引，须属于选中场景；与显式 position/target 互斥
 *   cameraPosition — 显式相机位置；必须与 cameraTarget 成对提供且两点不重合
 *   cameraTarget   — 显式相机目标；必须与 cameraPosition 成对提供
 *   cameraFov      — 显式透视相机垂直视场角（度），默认 45；仅显式 position/target 可用
 *   background     — 背景色，默认透明；接受 transparent 或 #RGB/#RRGGBB/#RRGGBBAA
 *   lighting       — auto 仅在选中场景无光照时补默认灯光；source 只用源文件光照
 *   interactive    — 是否启用查看交互；默认 false
 *   fallback       — 无法渲染时展示的兜底文案；只作为文案，不作为资源地址
 *
 * 相机优先级固定：显式 position/target → cameraIndex → 选中场景中按源索引排序的首个有效相机 → 自动取景。
 */
import { computed, useAttrs } from 'vue'
import { getRuntimePreloadedConfig, resolveResourcePath } from '@/core/utils/path'
import { normalizeAssetKey } from '@/core/shared/runtime-preview'
import ModelViewer from '@runtime-kit/internal/renderers/ModelViewer.vue'
import { resolveAssetFallbackMessage } from '@runtime-kit/internal/utils/asset-fallback'
import { DEFAULT_MODEL_FALLBACK_MESSAGE } from '@runtime-kit/internal/renderers/model3d/view-options'

// attrs 已在双分支模板中显式 v-bind="safeAttrs" 透传，关闭自动 fallthrough 避免重复继承与非单根告警。
defineOptions({ inheritAttrs: false })

interface Props {
  /** 资源逻辑名 `asset.name` */
  name: string
  /** 源文件场景索引 */
  sceneIndex?: number
  /** 源文件相机索引 */
  cameraIndex?: number
  /** 显式相机位置 */
  cameraPosition?: [number, number, number]
  /** 显式相机目标 */
  cameraTarget?: [number, number, number]
  /** 显式透视相机垂直视场角（度） */
  cameraFov?: number
  /** 背景色 */
  background?: string
  /** 光照来源 */
  lighting?: 'auto' | 'source'
  /** 是否启用查看交互 */
  interactive?: boolean
  /** 兜底文案 */
  fallback?: string
}

const props = withDefaults(defineProps<Props>(), {
  name: '',
  sceneIndex: undefined,
  cameraIndex: undefined,
  cameraPosition: undefined,
  cameraTarget: undefined,
  cameraFov: undefined,
  background: 'transparent',
  lighting: 'auto',
  interactive: false,
  fallback: DEFAULT_MODEL_FALLBACK_MESSAGE,
})

/** 透传属性的屏蔽清单：src 与运行时探针属性只能由组件内部产生。 */
const BLOCKED_ATTR_KEYS = new Set(['src'])
const BLOCKED_ATTR_PREFIXES = ['data-runtime-model-', 'data-runtime-kit-media']

/**
 * 过滤外部透传属性，避免覆盖内部解析的资源地址和导出/首帧探针契约。
 * @returns 可安全透传给内部渲染器或兜底容器的属性
 */
function filterSafeAttrs(attrs: Record<string, unknown>): Record<string, unknown> {
  const safe: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(attrs)) {
    if (BLOCKED_ATTR_KEYS.has(key) || BLOCKED_ATTR_PREFIXES.some(prefix => key.startsWith(prefix))) {
      continue
    }
    safe[key] = value
  }
  return safe
}

const attrs = useAttrs()
// 渲染时重新取值，确保父组件动态更新的 attrs 不会命中过期缓存。
const safeAttrs = (): Record<string, unknown> => filterSafeAttrs(attrs)
const fallbackMessage = computed(() => resolveAssetFallbackMessage(props.fallback, DEFAULT_MODEL_FALLBACK_MESSAGE))

/**
 * 解析 manifest 中的三维资源地址。
 *
 * 只接受已登记且 render_type=model3d 的逻辑资源名：URL、绝对/相对路径以及未登记名称
 * 一律返回空串，防止绕过资源索引直接加载任意地址。
 * @param rawName 资源逻辑名
 * @returns manifest 解析后的资源地址；不满足条件时为空串
 */
function resolveManifestModelSrc(rawName: string): string {
  const name = String(rawName || '').trim()
  if (!name || /^(?:[a-z][a-z0-9+.-]*:|\/|\.{1,2}\/)/i.test(name)) {
    return ''
  }
  const manifest = getRuntimePreloadedConfig()?.manifest
  if (!manifest) {
    return ''
  }
  const assetKey = normalizeAssetKey(name)
  if (!assetKey || !manifest.assets?.[assetKey]) {
    return ''
  }
  const metadata = manifest.asset_metadata?.[assetKey]
  if (!metadata || metadata.render_type !== 'model3d') {
    return ''
  }
  return resolveResourcePath(name)
}

const src = computed(() => resolveManifestModelSrc(props.name))
const canRender = computed(() => Boolean(src.value))
</script>

<style scoped>
.asset-model__fallback {
  box-sizing: border-box;
  display: flex;
  width: 100%;
  min-height: 120px;
  align-items: center;
  justify-content: center;
  padding: 12px;
  color: #64748b;
  font-size: 13px;
  text-align: center;
  background: #f8fafc;
}
</style>

<!--
  文件用途：AssetModel — 基于 manifest 资源名称渲染 Backend 托管的标准 glTF 2.0 / GLB 三维模型。
  传入 name（asset.name）即可，workspaceId、路径解析与 Three.js 引擎加载由内部自动完成。
-->
<template>
  <ModelViewer
    v-if="canRender"
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
    v-bind="$attrs"
  />
  <div v-else class="asset-model__fallback" v-bind="$attrs">{{ fallbackMessage }}</div>
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
 *   fallback       — 无法渲染时展示的兜底文案
 *
 * 相机优先级固定：显式 position/target → cameraIndex → 选中场景中按源索引排序的首个有效相机 → 自动取景。
 */
import { computed } from 'vue'
import { useAssetSrc } from '@runtime-kit/public/composables/assets/useAssetSrc.v1'
import ModelViewer from '@runtime-kit/internal/renderers/ModelViewer.vue'
import { resolveAssetFallbackMessage, resolveAssetFallbackUrl } from '@runtime-kit/internal/utils/asset-fallback'
import { DEFAULT_MODEL_FALLBACK_MESSAGE } from '@runtime-kit/internal/renderers/model3d/view-options'

// attrs 已在双分支模板中显式 v-bind="$attrs" 透传，关闭自动 fallthrough 避免重复继承与非单根告警。
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

const fallbackUrl = computed(() => resolveAssetFallbackUrl(props.fallback))
const fallbackMessage = computed(() => resolveAssetFallbackMessage(props.fallback, DEFAULT_MODEL_FALLBACK_MESSAGE))
const src = useAssetSrc(() => props.name, () => fallbackUrl.value)
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

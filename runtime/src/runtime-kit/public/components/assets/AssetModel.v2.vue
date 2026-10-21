<!--
  文件功能：AssetModel.v2 为页内时间轴提供不可交互的模型目标，片段与整体变换由时间轴驱动。
-->
<template>
  <AssetModelV1
    v-bind="$attrs"
    :name="name"
    :scene-index="sceneIndex"
    :camera-index="cameraIndex"
    :camera-position="cameraPosition"
    :camera-target="cameraTarget"
    :camera-fov="cameraFov"
    :background="background"
    :lighting="lighting"
    :interactive="false"
    :fallback="fallback"
    data-runtime-kit-motion="timeline"
  />
</template>

<script setup lang="ts">
/**
 * AssetModel.v2
 *
 * 使用示例：
 *   <AssetModel.v2 name="product" class="w-full h-80" />
 *
 * 与 v1 的差异：固定关闭查看交互，保留相机、场景与光照参数；片段采样与整体包装变换
 * 由页内时间轴独占。未声明时间轴时可继续使用 v1。
 */
import AssetModelV1 from './AssetModel.v1.vue'
import { DEFAULT_MODEL_FALLBACK_MESSAGE } from '@runtime-kit/internal/renderers/model3d/view-options'

defineOptions({ inheritAttrs: false })

interface Props {
  /** 资源逻辑名 `asset.name`。 */
  name: string
  /** 源文件场景索引。 */
  sceneIndex?: number
  /** 源文件相机索引。 */
  cameraIndex?: number
  /** 显式相机位置。 */
  cameraPosition?: [number, number, number]
  /** 显式相机目标。 */
  cameraTarget?: [number, number, number]
  /** 显式透视相机垂直视场角（度）。 */
  cameraFov?: number
  /** 背景色。 */
  background?: string
  /** 光照来源。 */
  lighting?: 'auto' | 'source'
  /** 兜底文案。 */
  fallback?: string
}

withDefaults(defineProps<Props>(), {
  name: '',
  sceneIndex: undefined,
  cameraIndex: undefined,
  cameraPosition: undefined,
  cameraTarget: undefined,
  cameraFov: undefined,
  background: 'transparent',
  lighting: 'auto',
  fallback: DEFAULT_MODEL_FALLBACK_MESSAGE,
})
</script>

<!--
  文件用途：AssetBackground — 将 Backend 托管资源设置为容器背景图。
  传入 name（asset.name）即可，workspaceId 和路径解析由内部自动完成。
-->
<template>
  <div :style="[backgroundStyle, sizeStyle, props.style]" :class="props.class" v-bind="$attrs">
    <slot />
  </div>
</template>

<script setup lang="ts">
/**
 * AssetBackground
 *
 * 使用示例：
 *   <AssetBackground name="background" class="hero-section">
 *     <h1>标题内容</h1>
 *   </AssetBackground>
 *
 *   <!-- 附加样式属性 -->
 *   <AssetBackground
 *     name="background.png"
 *     size="cover"
 *     position="center"
 *     :repeat="false"
 *   />
 *
 * Props:
 *   name     — 资源的逻辑名 `asset.name`（必传）
 *   fallback — 未命中 manifest 时的兜底图 URL（可选）
 *   size     — background-size，默认 "cover"
 *   position — background-position，默认 "center"
 *   repeat   — 是否平铺，默认 false（no-repeat）
 *   class    — 传给容器的 class
 *   style    — 传给容器的额外 style（会与背景样式合并）
 */
import { computed } from 'vue'
import { useAssetBackground } from '@runtime-kit/public/composables/assets/useAssetBackground.v1'

interface Props {
  /** 资源的逻辑名 `asset.name` */
  name: string
  /** 未命中 manifest 时的兜底图 URL */
  fallback?: string
  /** background-size，默认 "cover" */
  size?: string
  /** background-position，默认 "center" */
  position?: string
  /** 是否平铺，默认 false（no-repeat） */
  repeat?: boolean
  /** 传给容器的 class */
  class?: string | string[] | Record<string, boolean>
  /** 传给容器的额外内联 style */
  style?: string | Record<string, string>
}

const props = withDefaults(defineProps<Props>(), {
  fallback: '',
  size: 'cover',
  position: 'center',
  repeat: false,
  class: '',
  style: () => ({}),
})

/** 从 manifest 自动解析的背景图样式 */
const backgroundStyle = useAssetBackground(() => props.name, props.fallback)

/** background-size / position / repeat 的附加样式 */
const sizeStyle = computed(() => ({
  backgroundSize: props.size,
  backgroundPosition: props.position,
  backgroundRepeat: props.repeat ? 'repeat' : 'no-repeat',
}))
</script>

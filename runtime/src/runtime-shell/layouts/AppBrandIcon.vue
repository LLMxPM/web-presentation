<!-- 文件用途：按静态图标配置渲染应用品牌图标，始终保留原始图片颜色。 -->
<template>
  <img
    v-if="iconSrc"
    :src="iconSrc"
    :alt="resolvedAlt"
    class="app-brand-icon"
    :style="iconStyle"
  />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getIconConfig } from '@/core/utils/icon-registry'
import { resolveResourcePath } from '@/core/utils/path'

interface Props {
  /** 图标名称，对应 icons.config.yaml 中 static_icons.name */
  name?: string
  /** 图片尺寸，数字按 px 处理 */
  size?: number | string
  /** 图片替代文本 */
  alt?: string
}

const props = withDefaults(defineProps<Props>(), {
  name: '',
  size: 20,
  alt: '',
})

const iconSrc = ref('')
const iconDescription = ref('')
let loadVersion = 0

const normalizedName = computed(() => props.name?.trim() || '')

const resolvedAlt = computed(() => {
  return props.alt?.trim() || iconDescription.value || normalizedName.value || '应用图标'
})

const iconSize = computed(() => normalizeCssSize(props.size))

const iconStyle = computed(() => ({
  width: iconSize.value,
  height: iconSize.value,
}))

watch(normalizedName, loadIconSource, { immediate: true })

/**
 * 根据图标名读取静态图标配置，只取图片地址，不走通用 Icon 的 inline SVG 着色逻辑。
 */
async function loadIconSource(): Promise<void> {
  const currentVersion = ++loadVersion
  const iconName = normalizedName.value

  if (!iconName) {
    iconSrc.value = ''
    iconDescription.value = ''
    return
  }

  try {
    const iconConfig = await getIconConfig(iconName)
    if (currentVersion !== loadVersion) return

    iconSrc.value = iconConfig?.type === 'static' && iconConfig.src
      ? resolveResourcePath(iconConfig.src)
      : ''
    iconDescription.value = iconConfig?.description || iconName
  } catch {
    if (currentVersion !== loadVersion) return
    iconSrc.value = ''
    iconDescription.value = iconName
  }
}

/**
 * 规范化 CSS 尺寸值。
 * @param value 原始尺寸，数字和纯数字字符串会补 px
 * @returns 可直接用于样式的尺寸字符串
 */
function normalizeCssSize(value: number | string): string {
  if (typeof value === 'number') {
    return `${value}px`
  }
  if (/^\d+(\.\d+)?$/.test(value)) {
    return `${value}px`
  }
  return value
}
</script>

<style scoped>
.app-brand-icon {
  display: inline-block;
  object-fit: contain;
  max-width: 100%;
  max-height: 100%;
}
</style>

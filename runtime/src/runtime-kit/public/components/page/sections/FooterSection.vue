<!--
  文件用途：默认页脚区块，展示页脚文本、分隔线和页码信息。
-->

<template>
  <div
    class="w-full grid items-center text-secondary"
    :class="{ 'border-t border-border-subtle': showTopBorder }"
    :style="[footerStyle, { gridTemplateColumns: '1fr auto 1fr' }]"
  >
    <div
      class="flex items-center h-full"
      :class="contentPositionClass"
    >
      <slot name="footer">
        <div class="flex items-center">
          <Icon v-if="icon" :name="icon" class="mr-2" :class="iconClass" />
          <p v-if="text && !link" class="font-body leading-tight text-secondary m-0" :style="textStyle">{{ text }}</p>
          <a v-if="link" :href="link" target="_blank" class="font-body leading-tight text-secondary m-0" :style="textStyle">{{ linkText || text }}</a>
        </div>
      </slot>
    </div>

    <div
      v-if="showPagination"
      class="flex items-center h-full"
      :class="paginationPositionClass"
    >
      <Pagination v-bind="paginationProps" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Pagination from './Pagination.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'


defineOptions({
  name: 'FooterSection'
})

type FontSize = number | 'small' | 'medium' | 'large' | 'xl'
type AlignType = 'left' | 'center' | 'right'
type PaddingConfig =
  | number
  | {
      top?: number
      right?: number
      bottom?: number
      left?: number
    }
interface PaginationConfig {
  currentPage?: number
  totalPages?: number
  separator?: string
  showTotal?: boolean
  prefix?: string
  suffix?: string
}
interface Props {
  text?: string
  textSize?: FontSize
  align?: AlignType
  padding?: PaddingConfig
  showTopBorder?: boolean
  showPagination?: boolean
  paginationConfig?: PaginationConfig
  paginationAlign?: AlignType
  height?: number
  link?: string
  linkText?: string
  icon?: string // 新增：图标名称
}

const props = withDefaults(defineProps<Props>(), {
  text: '',
  textSize: 'medium',
  align: 'left',
  padding: 0,
  showTopBorder: true,
  showPagination: false,
  paginationConfig: () => ({}),
  paginationAlign: 'right',
  height: 50,
  link: '',
  linkText: '',
  icon: '' // 默认值
})

const contentPositionClass = computed(() => {
  switch (props.align) {
    case 'center':
      return 'col-center'
    case 'right':
      return 'col-right'
    default:
      return 'col-left'
  }
})

const paginationPositionClass = computed(() => {
  switch (props.paginationAlign) {
    case 'center':
      return 'col-center'
    case 'right':
      return 'col-right'
    default:
      return 'col-left'
  }
})

const convertFontSize = (size: FontSize): string => {
  if (typeof size === 'number') return `${size}px`
  const sizeMap = {
    small: '12px',
    medium: '14px',
    large: '16px',
    xl: '18px'
  }
  return sizeMap[size] || sizeMap.medium
}
/**
 * 转换padding配置为CSS padding值
 * 当传入数字时，只设置左右padding，上下padding固定为0
 * @param padding - padding配置，可以是数字或对象
 * @returns CSS padding字符串
 */
const convertPadding = (padding: PaddingConfig): string => {
  if (typeof padding === 'number') return `0 ${padding}px`
  const { top = 0, right = 0, bottom = 0, left = 0 } = padding
  return `${top}px ${right}px ${bottom}px ${left}px`
}
const textStyle = computed(() => ({
  fontSize: convertFontSize(props.textSize)
}))
const footerStyle = computed(() => ({
  padding: convertPadding(props.padding),
  height: `${props.height}px`
}))
const paginationProps = computed(() => ({ ...props.paginationConfig }))
const iconClass = computed(() => {
  if (typeof props.textSize === 'number') return 'size-4'
  const sizeMap = {
    small: 'size-2.5',
    medium: 'size-3',
    large: 'size-3.5',
    xl: 'size-4'
  }
  return sizeMap[props.textSize] || sizeMap.medium
})
</script>

<style scoped>
/* 位置控制类 */
.col-left {
  grid-column: 1; /* 放置在第1列 */
  justify-self: start; /* 在单元格内靠左 */
}

.col-center {
  grid-column: 2; /* 放置在第2列 */
  justify-self: center; /* 在单元格内居中 */
}

.col-right {
  grid-column: 3; /* 放置在第3列 */
  justify-self: end; /* 在单元格内靠右 */
}
</style>

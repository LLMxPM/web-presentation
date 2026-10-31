<!--
  文件用途：本地示例页，展示 AssetFormula 渲染 LaTeX 公式资源的块级与行内排版。
-->
<template>
  <ShowcasePage
    title="LaTeX 公式"
    subtitle="公式源码由 KaTeX 排版，页面只传入文本与显示模式"
    :capabilities="capabilities"
  >
    <div class="grid h-full min-h-0 grid-cols-[1.6fr_0.9fr] gap-5">
      <section class="flex min-h-0 flex-col rounded-lg border border-border-subtle bg-background-subtle p-5">
        <div class="mb-3 flex items-center gap-2">
          <Icon name="star" class="size-5 text-primary" />
          <h2 class="font-heading text-lg font-semibold text-primary">{{ currentFormula.label }}</h2>
          <span class="ml-auto font-body text-xs text-secondary">{{ displayMode ? '块级公式' : '行内公式' }}</span>
        </div>

        <div class="flex min-h-0 flex-1 items-center rounded-md border border-border bg-default p-4">
          <AssetFormula
            :content="currentFormula.content"
            :display-mode="displayMode"
            :show-border="showBorder"
            width="100%"
            min-height="180px"
            background-color="#ffffff"
            border-color="#cbd5e1"
            border-radius="12px"
            padding="24px"
          />
        </div>

        <div class="mt-3 flex items-center gap-6">
          <label class="flex items-center gap-2">
            <input v-model="displayMode" type="checkbox" class="size-4 accent-primary" />
            <span class="font-body text-xs text-primary">块级模式</span>
          </label>
          <label class="flex items-center gap-2">
            <input v-model="showBorder" type="checkbox" class="size-4 accent-primary" />
            <span class="font-body text-xs text-primary">显示渲染区域边框</span>
          </label>
          <span class="ml-auto font-body text-xs leading-6 text-secondary">{{ currentFormula.description }}</span>
        </div>
      </section>

      <section class="flex min-h-0 flex-col gap-4">
        <div class="rounded-lg border border-border bg-background-subtle p-5">
          <h3 class="mb-3 font-heading text-base font-semibold text-primary">公式预设</h3>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="preset in formulaPresets"
              :key="preset.key"
              type="button"
              class="rounded-md border px-3 py-2 font-body text-xs font-medium transition-colors"
              :class="selectedFormula === preset.key
                ? 'border-primary bg-primary-50 text-primary'
                : 'border-border text-secondary hover:border-primary-300'"
              @click="selectedFormula = preset.key"
            >
              {{ preset.label }}
            </button>
          </div>
        </div>

        <div class="flex min-h-0 flex-1 flex-col rounded-lg border border-border bg-background-subtle p-5">
          <h3 class="font-heading text-base font-semibold text-primary">公式源码</h3>
          <pre class="mt-3 max-h-[140px] overflow-auto rounded-md bg-default p-3 font-code text-xs leading-6 text-primary">{{ currentFormula.content }}</pre>
          <dl class="mt-3 space-y-1.5">
            <div v-for="row in paramRows" :key="row.name" class="flex gap-3 rounded-md bg-default px-3 py-1.5">
              <dt class="w-24 shrink-0 font-code text-xs text-primary">{{ row.name }}</dt>
              <dd class="min-w-0 flex-1 font-body text-xs leading-6 text-secondary">{{ row.note }}</dd>
            </div>
          </dl>
          <p class="mt-auto pt-2 font-body text-xs leading-6 text-secondary">
            行内公式用于正文中的符号说明；块级公式独占一行，适合推导过程。
          </p>
        </div>
      </section>
    </div>
  </ShowcasePage>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import ShowcasePage, { type ShowcaseCapability } from '@/examples/local/components/ShowcasePage.vue'
import AssetFormula from '@runtime-kit/public/components/assets/AssetFormula.v1.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'

type FormulaKey = 'quadratic' | 'bayes' | 'matrix' | 'integral'

interface FormulaPreset {
  key: FormulaKey
  label: string
  description: string
  content: string
}

const capabilities: ShowcaseCapability[] = [
  { name: 'AssetFormula.v1', path: '@runtime-kit/public/components/assets/AssetFormula.v1.vue' },
]

const selectedFormula = ref<FormulaKey>('quadratic')
const displayMode = ref(true)
const showBorder = ref(false)

const formulaPresets: FormulaPreset[] = [
  {
    key: 'quadratic',
    label: '二次方程',
    description: '上下标与分式的常见写法',
    content: 'x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}',
  },
  {
    key: 'bayes',
    label: '贝叶斯公式',
    description: '条件概率与分式结构',
    content: 'P(A \\mid B)=\\frac{P(B \\mid A)P(A)}{P(B)}',
  },
  {
    key: 'matrix',
    label: '矩阵乘法',
    description: '多行多列公式排版',
    content: '\\begin{bmatrix} a & b \\\\ c & d \\end{bmatrix}\\begin{bmatrix} x \\\\ y \\end{bmatrix}=\\begin{bmatrix} ax+by \\\\ cx+dy \\end{bmatrix}',
  },
  {
    key: 'integral',
    label: '高斯积分',
    description: '大型数学符号与积分区间',
    content: '\\int_{-\\infty}^{\\infty} e^{-x^2} \\, dx = \\sqrt{\\pi}',
  },
]

const currentFormula = computed(
  () => formulaPresets.find((item) => item.key === selectedFormula.value) || formulaPresets[0],
)

/** 渲染区域参数说明。 */
const paramRows = [
  { name: 'displayMode', note: 'true 为块级公式，false 为行内公式。' },
  { name: 'minHeight', note: '渲染区域最小高度，避免公式切换时页面抖动。' },
  { name: 'padding', note: '内边距，块级公式建议不小于 24px。' },
  { name: 'background', note: '渲染区域背景色，默认透明以继承页面背景。' },
]
</script>

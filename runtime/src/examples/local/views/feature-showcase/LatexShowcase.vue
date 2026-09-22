<!--
  文件用途：本地示例页，用于展示 LatexViewer 的公式排版与统一渲染区域参数。
-->
<template>
  <DefaultContentPage title="LaTeX 公式展示" subtitle="展示 LatexViewer 的 KaTeX 渲染能力">
    <template #content>
      <div class="space-y-6">
        <section class="grid grid-cols-[1.2fr_0.8fr] gap-6">
          <div class="rounded-lg border border-border bg-background-subtle p-5">
            <div class="mb-4 flex items-center gap-3">
              <Icon name="star" class="size-4" color="primary" />
              <h2 class="font-heading text-xl font-semibold text-primary">公式选择</h2>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <button
                v-for="preset in formulaPresets"
                :key="preset.key"
                type="button"
                class="formula-button"
                :class="{ 'formula-button--active': selectedFormula === preset.key }"
                @click="selectedFormula = preset.key"
              >
                {{ preset.label }}
              </button>
            </div>
          </div>

          <div class="rounded-lg border border-border bg-background-subtle p-5">
            <div class="mb-4 flex items-center gap-3">
              <Icon name="slider" class="size-4" color="primary" />
              <h2 class="font-heading text-xl font-semibold text-primary">显示参数</h2>
            </div>

            <div class="space-y-4 text-sm">
              <label class="flex items-center gap-3">
                <input v-model="displayMode" type="checkbox" class="h-4 w-4 accent-primary" />
                <span>块级公式模式</span>
              </label>
              <label class="flex items-center gap-3">
                <input v-model="showBorder" type="checkbox" class="h-4 w-4 accent-primary" />
                <span>显示渲染区域边框</span>
              </label>
            </div>
          </div>
        </section>

        <section class="rounded-lg border border-border bg-background p-6">
          <LatexViewer
            :content="currentFormula.content"
            :display-mode="displayMode"
            :show-border="showBorder"
            width="100%"
            min-height="160px"
            background-color="#ffffff"
            border-color="#cbd5e1"
            border-radius="14px"
            padding="28px"
          />
        </section>

        <section class="grid grid-cols-[1fr_1.2fr] gap-6">
          <div class="rounded-lg border border-border bg-background-subtle p-5">
            <h3 class="mb-3 font-heading text-lg font-semibold text-primary">{{ currentFormula.label }}</h3>
            <p class="text-sm leading-6 text-secondary">{{ currentFormula.description }}</p>
          </div>

          <pre class="formula-source">{{ currentFormula.content }}</pre>
        </section>
      </div>
    </template>
  </DefaultContentPage>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import DefaultContentPage from '@/runtime-kit/public/components/page/templates/DefaultContentPage.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'
import LatexViewer from '@runtime-kit/internal/renderers/LatexViewer.vue'

type FormulaKey = 'quadratic' | 'bayes' | 'matrix' | 'integral'

interface FormulaPreset {
  key: FormulaKey
  label: string
  description: string
  content: string
}

defineOptions({
  name: 'LatexShowcase',
})

const selectedFormula = ref<FormulaKey>('quadratic')
const displayMode = ref(true)
const showBorder = ref(true)

const formulaPresets: FormulaPreset[] = [
  {
    key: 'quadratic',
    label: '二次方程',
    description: '常见的二次方程求根公式，适合展示上下标和分式。',
    content: 'x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}',
  },
  {
    key: 'bayes',
    label: '贝叶斯公式',
    description: '概率表达式示例，适合展示条件概率与分式结构。',
    content: 'P(A \\mid B)=\\frac{P(B \\mid A)P(A)}{P(B)}',
  },
  {
    key: 'matrix',
    label: '矩阵乘法',
    description: '矩阵排版示例，适合展示多行多列公式。',
    content: '\\begin{bmatrix} a & b \\\\ c & d \\end{bmatrix}\\begin{bmatrix} x \\\\ y \\end{bmatrix}=\\begin{bmatrix} ax+by \\\\ cx+dy \\end{bmatrix}',
  },
  {
    key: 'integral',
    label: '高斯积分',
    description: '积分与指数表达式示例，适合展示大型数学符号。',
    content: '\\int_{-\\infty}^{\\infty} e^{-x^2} \\, dx = \\sqrt{\\pi}',
  },
]

/**
 * 当前选中的公式配置。
 * @returns 公式预设项
 */
const currentFormula = computed(() => {
  return formulaPresets.find(item => item.key === selectedFormula.value) || formulaPresets[0]
})
</script>

<style scoped>
.formula-button {
  min-height: 48px;
  border-radius: 8px;
  border: 1px solid var(--tw-color-border-default);
  background: var(--tw-color-bg-default);
  color: var(--tw-color-text-primary);
  font-weight: 600;
  transition: border-color 0.2s ease, background-color 0.2s ease;
}

.formula-button--active {
  border-color: var(--tw-color-text-primary);
  background: color-mix(in srgb, var(--tw-color-text-primary) 8%, transparent);
}

.formula-source {
  margin: 0;
  overflow: auto;
  border-radius: 8px;
  border: 1px solid var(--tw-color-border-subtle);
  background: color-mix(in srgb, var(--tw-color-bg-default) 92%, var(--tw-color-border-subtle));
  padding: 18px;
  color: var(--tw-color-text-primary);
  font-family: var(--tw-font-code), monospace;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
}
</style>

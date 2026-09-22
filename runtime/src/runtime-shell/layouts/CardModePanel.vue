<!--
  文件用途：运行时卡片模式面板，展示全部页面卡片并支持调整卡片尺寸。
-->

<template>
  <section class="card-mode" data-testid="card-mode" aria-label="卡片模式">
    <header class="card-mode__header">
      <div class="card-mode__heading">
        <p class="card-mode__eyebrow">页面浏览</p>
        <div class="card-mode__title-row">
          <h1>卡片模式</h1>
          <span>{{ pages.length }} 页</span>
        </div>
      </div>

      <div class="card-mode__actions">
        <label class="card-mode__size-control">
          <span>卡片大小</span>
          <input
            v-model.number="cardSize"
            type="range"
            min="140"
            max="420"
            step="10"
            aria-label="调整卡片大小"
          />
          <output>{{ cardSize }} px</output>
        </label>
        <button class="card-mode__close" type="button" aria-label="退出卡片模式" @click="emit('close')">
          <X :size="17" />
          <span>退出</span>
        </button>
      </div>
    </header>

    <div v-if="pages.length > 0" class="card-mode__body">
      <PresenterPageGrid
        :pages="pages"
        :current-path="currentPath"
        :tile-size="cardSize"
        @navigate="emit('select', $event)"
      />
    </div>

    <div v-else class="card-mode__empty">
      暂无可浏览页面
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { readRuntimePreference, writeRuntimePreference } from '@/core/utils/runtime-preferences'
import { X } from '@lucide/vue'

import PresenterPageGrid from '@/runtime-shell/presenter/PresenterPageGrid.vue'
import type { PresenterPage } from '@/runtime-shell/presenter/usePresenterController'

interface Props {
  pages: PresenterPage[]
  currentPath: string
}

defineProps<Props>()

const emit = defineEmits<{
  close: []
  select: [path: string]
}>()

const CARD_SIZE_STORAGE_KEY = 'web-presentation.card-mode.cardSize'
const DEFAULT_CARD_SIZE = 300
const MIN_CARD_SIZE = 140
const MAX_CARD_SIZE = 420
const cardSize = ref(readStoredCardSize())

watch(cardSize, (value) => {
  const normalizedValue = clampCardSize(value)
  if (normalizedValue !== value) {
    cardSize.value = normalizedValue
    return
  }
  writeStoredCardSize(normalizedValue)
})

/**
 * 读取已保存的卡片尺寸。
 * @returns 合法的卡片宽度
 */
function readStoredCardSize(): number {
  if (typeof localStorage === 'undefined') {
    return DEFAULT_CARD_SIZE
  }

  const storedText = readRuntimePreference(CARD_SIZE_STORAGE_KEY, '')
  if (!storedText) {
    return DEFAULT_CARD_SIZE
  }

  const storedValue = Number(storedText)
  return Number.isFinite(storedValue) ? clampCardSize(storedValue) : DEFAULT_CARD_SIZE
}

/**
 * 保存当前卡片尺寸，供下次进入卡片模式复用。
 * @param value 合法的卡片宽度
 */
function writeStoredCardSize(value: number): void {
  try {
    writeRuntimePreference(CARD_SIZE_STORAGE_KEY, String(value))
  } catch {
    // 本地存储不可用时仍保留本次会话内的尺寸变化。
  }
}

/**
 * 限制卡片尺寸范围并转换为十像素步长。
 * @param value 原始尺寸
 * @returns 规范化后的卡片宽度
 */
function clampCardSize(value: number): number {
  if (!Number.isFinite(value)) {
    return DEFAULT_CARD_SIZE
  }
  const steppedValue = Math.round(value / 10) * 10
  return Math.min(MAX_CARD_SIZE, Math.max(MIN_CARD_SIZE, steppedValue))
}
</script>

<style scoped>
.card-mode {
  position: fixed;
  inset: 0;
  z-index: 10020;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  background:
    radial-gradient(circle at 10% 0%, rgba(224, 231, 255, 0.82), transparent 30rem),
    #f8fafc;
  color: #0f172a;
}

.card-mode__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 1rem;
  min-height: 4.5rem;
  padding: 0.75rem 1.5rem;
  border-bottom: 1px solid #e2e8f0;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(14px);
}

.card-mode__heading,
.card-mode__actions,
.card-mode__title-row,
.card-mode__size-control,
.card-mode__close {
  display: flex;
  align-items: center;
}

.card-mode__heading {
  min-width: 0;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.125rem;
}

.card-mode__eyebrow {
  margin: 0;
  color: #64748b;
  font-size: 0.6875rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.card-mode__title-row {
  gap: 0.625rem;
}

.card-mode__title-row h1 {
  margin: 0;
  font-size: 1.25rem;
  line-height: 1.25;
}

.card-mode__title-row span {
  border-radius: 999px;
  background: #eef2ff;
  padding: 0.25rem 0.5rem;
  color: #4f46e5;
  font-size: 0.6875rem;
  font-weight: 800;
}

.card-mode__actions {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.75rem;
}

.card-mode__size-control {
  gap: 0.625rem;
  border: 1px solid #e2e8f0;
  border-radius: 0.625rem;
  background: white;
  padding: 0.5rem 0.75rem;
  color: #475569;
  font-size: 0.75rem;
  font-weight: 700;
}

.card-mode__size-control input {
  width: clamp(8rem, 16vw, 13rem);
  accent-color: #4f46e5;
}

.card-mode__size-control output {
  min-width: 3.5rem;
  color: #1e293b;
  text-align: right;
}

.card-mode__close {
  justify-content: center;
  gap: 0.375rem;
  height: 2.25rem;
  border: 1px solid #cbd5e1;
  border-radius: 0.625rem;
  background: white;
  padding: 0 0.75rem;
  color: #334155;
  font-size: 0.75rem;
  font-weight: 800;
  cursor: pointer;
}

.card-mode__close:hover {
  border-color: #a5b4fc;
  background: #eef2ff;
  color: #4338ca;
}

.card-mode__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
  font-size: 0.8125rem;
  text-align: center;
}

.card-mode__empty {
  flex: 1;
  min-height: 12rem;
}

.card-mode__body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 1.25rem 1.5rem 2rem;
  box-sizing: border-box;
}

@media (max-width: 640px) {
  .card-mode__header {
    align-items: stretch;
    flex-direction: column;
    padding: 0.75rem 1rem;
  }

  .card-mode__actions {
    justify-content: stretch;
  }

  .card-mode__size-control {
    flex: 1;
  }

  .card-mode__size-control input {
    min-width: 0;
    flex: 1;
  }

  .card-mode__body {
    padding: 1rem;
  }
}
</style>

<!-- 文件功能：展示带标题的只读 JSON 代码块，供配置与契约详情复用。 -->
<template>
  <div>
    <p class="mb-2 text-xs font-semibold text-text-muted">{{ title }}</p>
    <pre class="max-h-72 overflow-auto rounded-ui-md bg-surface-inverse p-3 text-[11px] leading-5 text-text-on-inverse">{{ formattedValue }}</pre>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ title: string; value: unknown }>()

const formattedValue = computed(() => JSON.stringify(props.value, null, 2))
</script>

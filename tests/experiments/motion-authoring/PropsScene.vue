<!-- 文件功能：Motion 声明式 Vue 交互样例；单独验证 props 写法，不将它冒充可任意定位的整页时间轴。 -->
<script setup lang="ts">
import { ref } from 'vue'
import { motion } from 'motion-v'
const expanded = ref(false)
</script>

<template>
  <button @click="expanded = !expanded">切换状态</button>
  <motion.div class="interactive-card" :animate="{ x: expanded ? 80 : 0, scale: expanded ? 1.1 : 1 }" :transition="{ duration: 0.2 }">
    用 Vue 状态直接描述交互
  </motion.div>
</template>

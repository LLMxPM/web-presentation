<!-- 文件功能：提供固定非交互的 Scene 模型组件与受限实例句柄，静态渲染继续复用 AssetModel.v1。 -->
<script lang="ts">
export type { ModelSceneComponent, ModelSceneHandle, ModelSceneAnimation } from '@/runtime-kit/internal/renderers/model3d/scene-contract'
</script>
<script setup lang="ts">
import { ref, type ComponentPublicInstance } from 'vue'
import AssetModelV1 from './AssetModel.v1.vue'
import { readModelSceneHandle } from '@/runtime-kit/internal/renderers/model3d/scene-contract'

defineOptions({ inheritAttrs: false })
defineProps<{ name: string }>()
const model = ref<ComponentPublicInstance | null>(null)
/** 只在本次模型完成真实首帧后返回句柄；资源替换后旧句柄自动失效。 */
function getHandle() { return readModelSceneHandle(model.value?.$el instanceof Element ? model.value.$el : null) }
defineExpose({ getHandle })
</script>
<template><AssetModelV1 ref="model" v-bind="$attrs" :name="name" :interactive="false" /></template>

<!-- 文件功能：根路由接管跳转，自动进入近期活跃工作空间（TailwindCSS 版）。 -->
<template>
  <div class="flex flex-col items-center justify-center h-full gap-6 animate-in fade-in duration-500">
    <!-- Pulsing Loader -->
    <div class="relative w-16 h-16">
      <div class="absolute inset-0 border-4 border-indigo-200 rounded-full"></div>
      <div class="absolute inset-0 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
    </div>
    
    <div class="text-center space-y-2">
      <span class="text-sm font-bold text-slate-500 uppercase tracking-widest animate-pulse transition-all">正在同步权限并加载工作空间</span>
      <p class="text-[10px] text-slate-300 font-mono">ANTICGRAVITY ENGINE V1.0 INITIALIZING...</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listWorkspaces } from '@/api/catalog'
import { Message } from '@/utils/message'
import { reportClientError } from '@/utils/client-logger'
import { buildWorkspaceHomePath } from '@/utils/workspace-routes'

const router = useRouter()

onMounted(async () => {
  try {
    // 延迟一秒模拟加载感（可选，这里保持原有逻辑）
    const res = await listWorkspaces({
      page: 1,
      page_size: 1,
      status: 'active',
      sort_by: 'last_opened_at',
      sort_order: 'desc',
    })
    if (res.items.length > 0) {
      router.replace(buildWorkspaceHomePath(res.items[0].id))
    } else {
      // 没有任何可进入的启用工作空间
      Message.warning('当前没有可进入的启用工作空间，请先恢复归档工作空间或联系管理员。')
    }
  } catch (error) {
    reportClientError(error, { message: '获取工作空间失败，请检查网络。', component: 'EntryView' })
  }
})
</script>

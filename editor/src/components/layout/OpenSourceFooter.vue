<!-- 文件功能：展示编辑器后台底栏中的开源项目信息与许可证披露。 -->
<template>
  <footer class="shrink-0 border-t border-slate-200/80 bg-slate-50/95 px-6 text-[11px] text-slate-500">
    <div class="mx-auto flex h-9 max-w-[1600px] items-center justify-between gap-4">
      <div class="flex min-w-0 items-center gap-2">
        <Github class="h-3.5 w-3.5 shrink-0 text-slate-500" aria-hidden="true" />
        <a
          class="inline-flex min-w-0 items-center gap-1 rounded-md px-1.5 py-1 font-semibold text-slate-700 transition-colors hover:bg-slate-100 hover:text-slate-950"
          href="https://github.com/LLMxPM/web-presentation"
          target="_blank"
          rel="noreferrer"
        >
          <span class="truncate">Web-Presentation</span>
          <ExternalLink class="h-3 w-3 shrink-0 text-slate-400" aria-hidden="true" />
        </a>
        <span class="hidden rounded border border-slate-200 bg-white px-1.5 py-0.5 font-medium text-slate-500 sm:inline">
          Apache License 2.0
        </span>
      </div>

      <div class="hidden min-w-0 items-center gap-2 text-slate-400 lg:flex">
        <span
          class="inline-flex shrink-0 items-center gap-1.5 rounded border border-slate-200 bg-white px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide text-slate-500"
          aria-label="runtime submodule"
        >
          <GitBranch class="h-3 w-3 text-slate-400" aria-hidden="true" />
          <span>runtime</span>
          <span class="h-1 w-1 rounded-full bg-slate-300" aria-hidden="true"></span>
          <span>submodule</span>
        </span>
        <a
          class="inline-flex min-w-0 items-center gap-1 rounded-md px-1.5 py-1 font-semibold text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
          href="https://github.com/LLMxPM/web-runtime-vue"
          target="_blank"
          rel="noreferrer"
        >
          <span class="truncate">web-runtime-vue</span>
          <ExternalLink class="h-3 w-3 shrink-0 text-slate-400" aria-hidden="true" />
        </a>
        <span class="rounded border border-slate-200 bg-white px-1.5 py-0.5 font-medium text-slate-500">
          AGPL-3.0-or-later
        </span>
      </div>
    </div>
  </footer>
</template>

<script setup lang="ts">
import { ExternalLink, GitBranch, Github } from 'lucide-vue-next'
</script>

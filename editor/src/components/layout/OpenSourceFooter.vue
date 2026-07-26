<!-- 文件功能：展示编辑器后台底栏中的开源项目信息与许可证披露。 -->
<template>
  <footer class="shrink-0 border-t border-border/80 bg-canvas/95 px-6 text-[11px] text-text-muted">
    <div class="mx-auto flex h-9 max-w-[1600px] items-center justify-between gap-4">
      <div class="flex min-w-0 items-center gap-2">
        <img :src="githubIconSrc" class="h-3.5 w-3.5 shrink-0 opacity-70" alt="" aria-hidden="true" />
        <a
          class="inline-flex min-w-0 items-center gap-1 rounded-md px-1.5 py-1 font-semibold text-text-emphasis transition-colors hover:bg-surface-muted hover:text-text-strong"
          href="https://github.com/LLMxPM/web-presentation"
          target="_blank"
          rel="noreferrer"
        >
          <span class="truncate">Web-Presentation</span>
          <ExternalLink class="h-3 w-3 shrink-0 text-text-disabled" aria-hidden="true" />
        </a>
        <span class="hidden rounded border border-border bg-surface px-1.5 py-0.5 font-medium text-text-muted sm:inline">
          Apache License 2.0
        </span>
      </div>

      <div class="hidden min-w-0 items-center gap-2 text-text-disabled lg:flex">
        <span
          class="inline-flex shrink-0 items-center gap-1.5 rounded border border-border bg-surface px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide text-text-muted"
          aria-label="runtime submodule"
        >
          <GitBranch class="h-3 w-3 text-text-disabled" aria-hidden="true" />
          <span>runtime</span>
          <span class="h-1 w-1 rounded-full bg-border-strong" aria-hidden="true"></span>
          <span>submodule</span>
        </span>
        <a
          class="inline-flex min-w-0 items-center gap-1 rounded-md px-1.5 py-1 font-semibold text-text-secondary transition-colors hover:bg-surface-muted hover:text-text-strong"
          href="https://github.com/LLMxPM/web-runtime-vue"
          target="_blank"
          rel="noreferrer"
        >
          <span class="truncate">web-runtime-vue</span>
          <ExternalLink class="h-3 w-3 shrink-0 text-text-disabled" aria-hidden="true" />
        </a>
        <span class="rounded border border-border bg-surface px-1.5 py-0.5 font-medium text-text-muted">
          AGPL-3.0-or-later
        </span>
      </div>
    </div>
  </footer>
</template>

<script setup lang="ts">
import { ExternalLink, GitBranch } from '@lucide/vue'

const githubIconSrc = `${import.meta.env.BASE_URL}github.svg`
</script>

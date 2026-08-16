<!-- 文件功能：渲染内容助手活跃 Run 的当前任务焦点状态。 -->
<template>
  <div class="agent-scope-status relative isolate inline-flex h-7 min-w-0 max-w-[176px] items-center gap-2 px-0.5 text-xs text-text-secondary" :title="tooltip" role="status">
    <span class="agent-scope-orb" aria-hidden="true">
      <span class="agent-scope-orb__fluid" />
      <span class="agent-scope-orb__light" />
    </span>
    <span class="agent-scope-status__content relative z-[1] inline-flex min-w-0 items-center gap-1.5">
      <span class="agent-scope-status__text-sheen" aria-hidden="true" />
      <span class="shrink-0 text-[10px] font-semibold text-text-emphasis">{{ typeLabel }}</span>
      <span class="h-3 w-px shrink-0 bg-border" />
      <span class="min-w-0 truncate text-[11px] font-semibold text-text">{{ label }}</span>
    </span>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  typeLabel: string
  label: string
  tooltip: string
}>()
</script>

<style scoped>
.agent-scope-orb {
  position: relative;
  z-index: 1;
  display: inline-flex;
  height: 1.5rem;
  width: 1.5rem;
  flex-shrink: 0;
  overflow: hidden;
  align-items: center;
  justify-content: center;
  border: 1px solid rgb(var(--ui-accent-border) / 0.85);
  border-radius: 9999px;
  background: rgb(var(--ui-surface-inverse));
  box-shadow:
    0 0 0 1px rgb(var(--ui-surface) / 0.75),
    0 0 6px rgb(var(--ui-accent) / 0.22);
}

.agent-scope-orb__fluid {
  position: absolute;
  inset: -12%;
  background: linear-gradient(145deg, rgb(var(--ui-accent-emphasis)), rgb(var(--ui-accent)) 64%);
  transform: translate3d(-8%, 5%, 0) rotate(-12deg) scale(1.04);
  animation: agent-scope-orb-flow 4s cubic-bezier(0.42, 0, 0.58, 1) infinite alternate;
}

.agent-scope-orb__light {
  position: absolute;
  top: 10%;
  left: 12%;
  height: 34%;
  width: 40%;
  border-radius: 9999px;
  background: radial-gradient(ellipse, rgb(var(--ui-surface) / 0.92) 0 22%, rgb(var(--ui-surface) / 0.24) 46%, transparent 76%);
  filter: blur(0.35px);
  opacity: 0.72;
  animation: agent-scope-orb-light-path 3.6s cubic-bezier(0.45, 0.05, 0.55, 0.95) infinite;
}

.agent-scope-status__content {
  overflow: hidden;
  border-radius: var(--ui-radius-sm);
}

.agent-scope-status__text-sheen {
  position: absolute;
  top: -44%;
  bottom: -44%;
  left: -66%;
  width: 42%;
  background: linear-gradient(108deg, transparent 0 30%, rgb(var(--ui-surface) / 0.78) 50%, transparent 70%);
  filter: blur(1px);
  opacity: 0;
  transform: rotate(22deg);
  pointer-events: none;
  animation: agent-scope-text-sheen 4.2s ease-in-out infinite;
}

@keyframes agent-scope-orb-flow {
  0% {
    transform: translate3d(-8%, 5%, 0) rotate(-12deg) scale(1.04);
  }

  50% {
    transform: translate3d(8%, -7%, 0) rotate(5deg) scale(1.12);
  }

  100% {
    transform: translate3d(14%, 8%, 0) rotate(16deg) scale(1.06);
  }
}

@keyframes agent-scope-orb-light-path {
  0%,
  100% {
    opacity: 0.58;
    transform: translate3d(0, 0, 0) scale(0.92);
  }

  24% {
    opacity: 0.88;
    transform: translate3d(5px, 1px, 0) scale(1.04);
  }

  52% {
    opacity: 0.7;
    transform: translate3d(8px, 7px, 0) scale(0.82);
  }

  78% {
    opacity: 0.82;
    transform: translate3d(3px, 12px, 0) scale(0.96);
  }
}

@keyframes agent-scope-text-sheen {
  0%,
  22% {
    opacity: 0;
    transform: translate3d(-18%, 0, 0) rotate(22deg);
  }

  45%,
  62% {
    opacity: 0.78;
  }

  84%,
  100% {
    opacity: 0;
    transform: translate3d(520%, 0, 0) rotate(22deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .agent-scope-orb__fluid,
  .agent-scope-orb__light,
  .agent-scope-status__text-sheen {
    animation: none;
  }
}
</style>

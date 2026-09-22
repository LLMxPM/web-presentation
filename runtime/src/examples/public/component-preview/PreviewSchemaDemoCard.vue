<!-- 文件用途：演示工作空间共享组件在预览场景中如何消费 props、slots，并用注释给出代表性 previewSchema 配置。 -->
<template>
  <section class="demo-card" :class="toneClass">
    <header class="demo-card__header">
      <div>
        <p class="demo-card__eyebrow">{{ badgeText }}</p>
        <h2 class="demo-card__title">{{ title }}</h2>
        <p v-if="subtitle" class="demo-card__subtitle">{{ subtitle }}</p>
      </div>
      <div class="demo-card__actions">
        <slot name="actions">
          <button class="demo-card__action-button" type="button">默认操作</button>
        </slot>
      </div>
    </header>

    <div v-if="showDivider" class="demo-card__divider"></div>

    <section class="demo-card__metrics">
      <article v-for="item in stats" :key="item.label" class="demo-card__metric">
        <span class="demo-card__metric-label">{{ item.label }}</span>
        <strong class="demo-card__metric-value">{{ item.value }}</strong>
        <span v-if="item.trend" class="demo-card__metric-trend">{{ item.trend }}</span>
      </article>
    </section>

    <section v-if="$slots.default" class="demo-card__body">
      <slot />
    </section>

    <footer v-if="$slots.footer" class="demo-card__footer">
      <slot name="footer" />
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/**
 * 预览配置 Schema 示例：
 *
 * 1. `previewSchema` 不写在组件运行时代码里，而是复制下方 JSON 到组件管理后台的
 *    “预览配置 Schema”编辑器，由 Backend 单独保存并随组件预览配置下发。
 * 2. `props` 的键名应与 `defineProps` 保持一致；`default` 会成为预览面板和 iframe
 *    初始渲染状态。
 * 3. `slots` 使用声明式节点数组，支持 `text`、`html`、`component`。`component`
 *    只能引用 Runtime Kit manifest 公开路径或 `@workspace-components/<code>/v/<version>`。
 * 4. `mocks` 是预览宿主静态状态示例，不会自动作为 props 传入组件；普通组件应优先
 *    将可调数据建模为 props 或 slots。
 * 5. `presets` 只写需要覆盖的字段，未覆盖字段会回退到 schema 默认值。
 *
 * {
 *   "props": {
 *     "title": {
 *       "type": "string",
 *       "label": "主标题",
 *       "description": "卡片首屏标题，通常对应组件的核心业务对象。",
 *       "required": true,
 *       "default": "季度经营看板",
 *       "placeholder": "请输入看板标题"
 *     },
 *     "subtitle": {
 *       "type": "textarea",
 *       "label": "副标题",
 *       "description": "展示在标题下方的补充说明，适合较长文案。",
 *       "default": "按客户增长、续费与风险信号汇总本季度表现。"
 *     },
 *     "badgeText": {
 *       "type": "string",
 *       "label": "角标文案",
 *       "default": "业务快照"
 *     },
 *     "tone": {
 *       "type": "select",
 *       "label": "视觉语义",
 *       "description": "用于验证枚举 props 与样式分支是否匹配。",
 *       "default": "primary",
 *       "options": [
 *         { "label": "主色", "value": "primary" },
 *         { "label": "成功", "value": "success" },
 *         { "label": "警示", "value": "warning" }
 *       ]
 *     },
 *     "showDivider": {
 *       "type": "boolean",
 *       "label": "显示分割线",
 *       "default": true
 *     },
 *     "metrics": {
 *       "type": "json",
 *       "label": "指标列表",
 *       "description": "复杂数组建议使用 json 字段，结构应与组件 props 类型一致。",
 *       "default": [
 *         { "label": "新增客户", "value": 128, "trend": "+18%" },
 *         { "label": "续费率", "value": "84%", "trend": "+6%" },
 *         { "label": "风险账户", "value": 7, "trend": "-3" }
 *       ]
 *     }
 *   },
 *   "slots": {
 *     "actions": {
 *       "label": "右上角操作区",
 *       "description": "具名插槽示例，可放按钮、图标或工作空间组件。",
 *       "default": [
 *         {
 *           "type": "html",
 *           "value": "<button style='border:0;border-radius:999px;padding:10px 16px;background:#0f172a;color:#fff;font-weight:700;'>查看详情</button>"
 *         }
 *       ]
 *     },
 *     "default": {
 *       "label": "正文内容",
 *       "description": "默认插槽示例，适合放正文说明或富文本摘要。",
 *       "default": [
 *         {
 *           "type": "html",
 *           "value": "<p style='margin:0;'>本季度新增客户主要来自企业服务与渠道合作，续费风险集中在长尾账户。</p>"
 *         }
 *       ]
 *     },
 *     "footer": {
 *       "label": "底部说明",
 *       "description": "混合 text 与 component 节点，演示 slot 节点组合。",
 *       "default": [
 *         { "type": "text", "value": "数据更新时间：09:30  " },
 *         {
 *           "type": "component",
 *           "component": "@runtime-kit/public/components/primitives/Icon.v1.vue",
 *           "props": { "name": "home", "size": 14, "color": "#64748b" }
 *         }
 *       ]
 *     }
 *   },
 *   "mocks": {
 *     "metricsResponse": {
 *       "label": "指标接口响应",
 *       "description": "仅演示预览静态状态的配置形状；当前组件实际通过 metrics prop 接收数据。",
 *       "default": {
 *         "status": "ok",
 *         "updatedAt": "09:30",
 *         "items": [
 *           { "label": "新增客户", "value": 128 },
 *           { "label": "续费率", "value": "84%" }
 *         ]
 *       }
 *     }
 *   },
 *   "presets": [
 *     {
 *       "key": "growth",
 *       "label": "增长态",
 *       "description": "强调正向增长数据。",
 *       "props": {
 *         "title": "增长业务看板",
 *         "tone": "success",
 *         "metrics": [
 *           { "label": "新增客户", "value": 246, "trend": "+32%" },
 *           { "label": "客单价", "value": "18.6万", "trend": "+9%" },
 *           { "label": "线索转化", "value": "41%", "trend": "+5%" }
 *         ]
 *       }
 *     },
 *     {
 *       "key": "risk",
 *       "label": "风险态",
 *       "description": "强调告警与待跟进事项。",
 *       "props": {
 *         "title": "续费风险看板",
 *         "tone": "warning",
 *         "showDivider": true,
 *         "metrics": [
 *           { "label": "风险账户", "value": 23, "trend": "+12" },
 *           { "label": "预计流失", "value": "86万", "trend": "+18%" },
 *           { "label": "已跟进", "value": "61%", "trend": "+7%" }
 *         ]
 *       },
 *       "slots": {
 *         "default": [
 *           {
 *             "type": "html",
 *             "value": "<p style='margin:0;color:#92400e;'>请优先跟进合同到期小于 30 天且活跃度下降的客户。</p>"
 *           }
 *         ]
 *       }
 *     }
 *   ]
 * }
 */
interface MetricItem {
  label: string
  value: string | number
  trend?: string
}

const props = withDefaults(defineProps<{
  title?: string
  subtitle?: string
  badgeText?: string
  tone?: 'primary' | 'success' | 'warning'
  showDivider?: boolean
  metrics?: MetricItem[]
}>(), {
  title: '季度经营看板',
  subtitle: '',
  badgeText: '业务快照',
  tone: 'primary',
  showDivider: true,
  metrics: () => [
    { label: '新增客户', value: 0, trend: '0%' },
    { label: '续费率', value: '0%', trend: '0%' },
  ],
})

const stats = computed(() => props.metrics)
const toneClass = computed(() => ({
  'demo-card--success': props.tone === 'success',
  'demo-card--warning': props.tone === 'warning',
}))
</script>

<style scoped>
.demo-card {
  width: 100%;
  padding: 28px;
  border-radius: 24px;
  background: linear-gradient(135deg, #ffffff 0%, #eff6ff 100%);
  border: 1px solid #dbeafe;
  box-shadow: 0 20px 48px rgba(15, 23, 42, 0.08);
  color: #0f172a;
  box-sizing: border-box;
}

.demo-card--success {
  background: linear-gradient(135deg, #ffffff 0%, #ecfdf5 100%);
  border-color: #bbf7d0;
}

.demo-card--warning {
  background: linear-gradient(135deg, #ffffff 0%, #fff7ed 100%);
  border-color: #fed7aa;
}

.demo-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
}

.demo-card__eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #64748b;
}

.demo-card__title {
  margin: 0;
  font-size: 32px;
  line-height: 1.2;
}

.demo-card__subtitle {
  margin: 10px 0 0;
  font-size: 15px;
  line-height: 1.7;
  color: #475569;
}

.demo-card__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 36px;
}

.demo-card__action-button {
  border: none;
  border-radius: 999px;
  padding: 10px 16px;
  background: #0f172a;
  color: #ffffff;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.demo-card__divider {
  margin: 20px 0 18px;
  height: 1px;
  background: rgba(148, 163, 184, 0.28);
}

.demo-card__metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.demo-card__metric {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.demo-card__metric-label {
  font-size: 12px;
  color: #64748b;
}

.demo-card__metric-value {
  font-size: 26px;
  line-height: 1.1;
}

.demo-card__metric-trend {
  font-size: 12px;
  font-weight: 700;
  color: #2563eb;
}

.demo-card__body {
  margin-top: 18px;
  font-size: 15px;
  line-height: 1.8;
  color: #334155;
}

.demo-card__footer {
  margin-top: 18px;
  font-size: 13px;
  line-height: 1.7;
  color: #475569;
}
</style>

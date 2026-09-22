<template>
  <DefaultContentPage title="Mermaid 图表展示" subtitle="支持各类 Mermaid 图表的渲染">
    <template #content>
      <div class="space-y-8 p-6">
        <!-- 控制面板 -->
        <section class="bg-background-subtle border border-border-subtle rounded-lg p-6">
          <div class="flex items-center mb-4">
            <Icon name="star" class="mr-3 size-5 text-primary" />
            <h2 class="font-heading text-xl font-bold text-primary">图表控制面板</h2>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <!-- 主题选择 -->
            <div>
              <label class="block text-sm font-medium text-primary mb-2">主题</label>
              <select
v-model="selectedTheme"
                class="w-full px-3 py-2 border border-border rounded-md bg-background text-primary focus:outline-none focus:ring-2 focus:ring-primary-300">
                <option value="default">默认</option>
                <option value="dark">深色</option>
                <option value="forest">森林</option>
                <option value="neutral">中性</option>
              </select>
            </div>

            <!-- 图表类型选择 -->
            <div>
              <label class="block text-sm font-medium text-primary mb-2">图表类型</label>
              <select
v-model="selectedDiagramType"
                class="w-full px-3 py-2 border border-border rounded-md bg-background text-primary focus:outline-none focus:ring-2 focus:ring-primary-300">
                <option value="flowchart">流程图</option>
                <option value="sequence">时序图</option>
                <option value="gantt">甘特图</option>
                <option value="pie">饼图</option>
                <option value="state">状态图</option>
                <option value="er">实体关系图</option>
                <option value="journey">用户旅程图</option>
              </select>
            </div>

            <!-- 操作按钮 -->
            <div class="flex space-x-2 items-end">
              <button
class="px-4 py-2 bg-background border border-border text-primary rounded-md hover:bg-primary-600 transition-colors text-sm"
                @click="refreshDiagram">
                刷新
              </button>
            </div>
          </div>
        </section>

        <!-- 当前图表展示 -->
        <section class="bg-background border border-border rounded-lg overflow-hidden">
          <div class="bg-background-subtle px-6 py-4 border-b border-border">
            <div class="flex items-center justify-between">
              <div class="flex items-center">
                <Icon name="star" class="mr-3 size-5 text-primary" />
                <h2 class="font-heading text-xl font-bold text-primary">
                  {{ diagramTypes[selectedDiagramType].title }}
                </h2>
              </div>
              <div class="text-sm text-secondary">
                {{ diagramTypes[selectedDiagramType].description }}
              </div>
            </div>
          </div>

          <div class="p-6">
            <MermaidViewer
ref="mermaidViewer" :content="currentDiagramContent" :theme="selectedTheme" height="500px"
              width="100%" />
          </div>
        </section>



      </div>
    </template>
  </DefaultContentPage>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import DefaultContentPage from '@/runtime-kit/public/components/page/templates/DefaultContentPage.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'
import MermaidViewer from '@runtime-kit/internal/renderers/MermaidViewer.vue'

defineOptions({
  name: 'MermaidShowcase'
})

// 响应式数据
const selectedTheme = ref<'default' | 'dark' | 'forest' | 'neutral'>('default')
const selectedDiagramType = ref('flowchart')
const mermaidViewer = ref()

// 图表类型定义
const diagramTypes = {
  flowchart: {
    title: '流程图',
    description: '展示业务流程和决策逻辑',
    content: `flowchart TD
    A[开始] --> B{是否登录?}
    B -->|是| C[进入主页]
    B -->|否| D[跳转登录页]
    D --> E[输入用户名密码]
    E --> F{验证成功?}
    F -->|是| C
    F -->|否| G[显示错误信息]
    G --> E
    C --> H[浏览内容]
    H --> I[结束]`
  },
  sequence: {
    title: '时序图',
    description: '展示对象间的交互时序',
    content: `sequenceDiagram
    participant U as 用户
    participant F as 前端
    participant B as 后端
    participant D as 数据库;  
    
    U->>F: 点击登录按钮
    F->>B: 发送登录请求
    B->>D: 查询用户信息
    D-->>B: 返回用户数据
    B-->>F: 返回登录结果
    F-->>U: 显示登录状态`
  },
  gantt: {
    title: '甘特图',
    description: '展示项目进度和时间安排',
    content: `gantt
    title 项目开发计划
    dateFormat  YYYY-MM-DD
    section 需求分析
    需求收集           :done,    des1, 2024-01-01,2024-01-05
    需求分析           :done,    des2, 2024-01-06, 3d
    需求评审           :active,  des3, 2024-01-10, 2d
    section 设计阶段
    UI设计            :         des4, after des3, 5d
    架构设计           :         des5, after des3, 3d
    section 开发阶段
    前端开发           :         dev1, after des4, 10d
    后端开发           :         dev2, after des5, 8d
    测试              :         test1, after dev1, 5d`
  },
  pie: {
    title: '饼图',
    description: '展示数据的比例分布',
    content: `pie title 技术栈使用比例
    "Vue.js" : 35
    "TypeScript" : 25
    "Tailwind CSS" : 20
    "Vite" : 15
    "其他" : 5`
  },
  state: {
    title: '状态图',
    description: '展示状态转换和生命周期',
    content: `stateDiagram-v2
    [*] --> 未登录
    未登录 --> 登录中 : 点击登录
    登录中 --> 已登录 : 验证成功
    登录中 --> 未登录 : 验证失败
    已登录 --> 浏览中 : 进入主页
    浏览中 --> 购物车 : 添加商品
    购物车 --> 结算中 : 点击结算
    结算中 --> 支付中 : 确认订单
    支付中 --> 已完成 : 支付成功
    支付中 --> 购物车 : 支付失败
    已完成 --> [*]`
  },
  er: {
    title: '实体关系图',
    description: '展示数据库实体关系',
    content: `erDiagram
    USER ||--o{ ORDER : places
    USER {
        int id PK
        string name
        string email
        datetime created_at
    }
    ORDER ||--|{ ORDER_ITEM : contains
    ORDER {
        int id PK
        int user_id FK
        datetime order_date
        decimal total_amount
    }
    PRODUCT ||--o{ ORDER_ITEM : "ordered in"
    PRODUCT {
        int id PK
        string name
        decimal price
        text description
    }
    ORDER_ITEM {
        int order_id FK
        int product_id FK
        int quantity
        decimal unit_price
    }`
  },
  journey: {
    title: '用户旅程图',
    description: '展示用户体验流程',
    content: `journey
    title 用户购物体验旅程
    section 发现阶段
      浏览网站        : 5: 用户
      搜索商品        : 4: 用户
      查看详情        : 5: 用户
    section 决策阶段
      比较价格        : 3: 用户
      查看评价        : 4: 用户
      添加购物车      : 5: 用户
    section 购买阶段
      填写信息        : 3: 用户
      选择支付        : 4: 用户
      完成支付        : 5: 用户
    section 售后阶段
      收到商品        : 5: 用户
      使用体验        : 4: 用户
      评价反馈        : 3: 用户`
  }
}

// 计算当前图表内容
const currentDiagramContent = computed(() => {
  return diagramTypes[selectedDiagramType.value]?.content || ''
})

/**
 * 刷新图表
 */
const refreshDiagram = async () => {
  if (mermaidViewer.value) {
    await nextTick()
    mermaidViewer.value.reload()
  }
}
</script>

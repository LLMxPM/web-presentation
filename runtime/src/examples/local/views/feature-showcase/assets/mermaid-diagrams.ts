/**
 * 文件用途：集中维护 Mermaid 示例图表源码，避免示例页模板被长文本撑开。
 */

export type MermaidDiagramKey = 'flowchart' | 'sequence' | 'gantt' | 'pie' | 'state' | 'er' | 'journey'

export interface MermaidDiagramPreset {
  /** 图表类型标识 */
  key: MermaidDiagramKey
  /** 中文名称 */
  label: string
  /** 适用场景说明 */
  description: string
  /** Mermaid 源码 */
  content: string
}

export const MERMAID_DIAGRAMS: MermaidDiagramPreset[] = [
  {
    key: 'flowchart',
    label: '流程图',
    description: '业务流程与决策分支',
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
    H --> I[结束]`,
  },
  {
    key: 'sequence',
    label: '时序图',
    description: '对象间的交互时序',
    content: `sequenceDiagram
    participant U as 用户
    participant F as 前端
    participant B as 后端
    participant D as 数据库
    U->>F: 点击登录按钮
    F->>B: 发送登录请求
    B->>D: 查询用户信息
    D-->>B: 返回用户数据
    B-->>F: 返回登录结果
    F-->>U: 显示登录状态`,
  },
  {
    key: 'gantt',
    label: '甘特图',
    description: '项目进度与时间安排',
    content: `gantt
    title 项目开发计划
    dateFormat  YYYY-MM-DD
    section 需求分析
    需求收集           :done,    des1, 2024-01-01, 5d
    需求分析           :done,    des2, after des1, 3d
    需求评审           :active,  des3, after des2, 2d
    section 设计阶段
    UI设计            :         des4, after des3, 5d
    架构设计           :         des5, after des3, 3d
    section 开发阶段
    前端开发           :         dev1, after des4, 10d
    后端开发           :         dev2, after des5, 8d
    测试              :         test1, after dev1, 5d`,
  },
  {
    key: 'pie',
    label: '饼图',
    description: '数据比例分布',
    content: `pie title 技术栈使用比例
    "Vue.js" : 35
    "TypeScript" : 25
    "Tailwind CSS" : 20
    "Vite" : 15
    "其他" : 5`,
  },
  {
    key: 'state',
    label: '状态图',
    description: '状态转换与生命周期',
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
    已完成 --> [*]`,
  },
  {
    key: 'er',
    label: '实体关系图',
    description: '数据库实体与关系',
    content: `erDiagram
    USER ||--o{ ORDER : places
    USER {
        int id PK
        string name
        string email
    }
    ORDER ||--|{ ORDER_ITEM : contains
    ORDER {
        int id PK
        int user_id FK
        decimal total_amount
    }
    PRODUCT ||--o{ ORDER_ITEM : "ordered in"
    PRODUCT {
        int id PK
        string name
        decimal price
    }`,
  },
  {
    key: 'journey',
    label: '用户旅程图',
    description: '体验阶段与情绪曲线',
    content: `journey
    title 用户购物体验旅程
    section 发现阶段
      浏览网站        : 5: 用户
      搜索商品        : 4: 用户
      查看详情        : 5: 用户
    section 决策阶段
      比较价格        : 3: 用户
      添加购物车      : 5: 用户
    section 购买阶段
      填写信息        : 3: 用户
      完成支付        : 5: 用户`,
  },
]

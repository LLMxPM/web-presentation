# 演示文稿创作路径对比

本文对比的不是单一工具类型，而是几类常见演示文稿创作路径：传统 Keynote/PowerPoint、套模板的 AI PPT、Codex/Claude Code + PPT skills、通用内容生成 skills，以及 `web-presentation` 的平台化创作路线。文档也会拆开说明这些路径背后的 AI 创作技术路线：直接改 PPTX/OOXML、生成 HTML、生成整张图片、代码生成 PPTX，以及混合式 Runtime。

核心问题不是“哪个工具更强”，而是：内容资产是否需要长期沉淀、AI 是否需要稳定项目上下文、产物是否要被持续编辑和构建、团队是否需要权限隔离与私有化部署。

## 核心结论

- 传统 Keynote/PowerPoint 仍然是逐页精修、现场演示、模板规范和最终文件交付最稳的路径。
- 套模板的 AI PPT 工具适合把 prompt、文档、大纲或品牌模板快速转成初稿，重点是缩短从空白页到可编辑 deck 的时间。
- Codex/Claude Code + PPT skills 更适合高定制、强过程控制和复杂素材处理，可以把研究、文案、视觉、渲染和 QA 写成可执行工作流。
- AI 演示创作的技术路线差异很大：OOXML 直改偏原生可编辑，HTML 生成偏视觉和运行态，图片生成偏视觉表达，混合式平台则偏资产治理和上下文稳定。
- `web-presentation` 的目标不是替代这些路径，而是把页面、资源、组件、主题、样式、AI Agent、预览和构建纳入同一个平台模型，服务长期项目和团队资产复用。

## 调研口径

本次调研把“AI 做演示文稿”拆成三层看：

- **产品形态**：用户直接看到的是 PowerPoint/Keynote、AI PPT 生成器、在线设计平台、Google Slides/PowerPoint 插件、Agent 工作台或私有化平台。
- **skill 形态**：Agent 侧看到的是 `SKILL.md`、工具披露、脚本、参考资料、模板、渲染检查和文件导出流程。Claude 官方已有 PowerPoint presentation generation 等内置 skill；OpenAI 的 skills catalog 也把 system、curated、experimental skill 分层管理。
- **技术路线**：真正决定产物边界的是 PPTX/OOXML、HTML/CSS/JS、图片生成、截图、PPTX SDK、Runtime 预览和平台数据模型。

这三层经常混在一起。例如“AI PPT 工具”可能底层是模板 + 专有编辑器 + PPTX 导出；“PPT skill”可能底层是 python-pptx、PptxGenJS、artifact-tool、HTML 截图或直接 OOXML 修改；“HTML deck”可能最后以 PDF、PNG 或 PPTX 形式交付。

## 产品、skills 与工具图谱

| 形态 | 代表产品 / skills / 工具 | 主要技术路线 | 适合场景 | 主要边界 |
| :--- | :--- | :--- | :--- | :--- |
| 传统演示软件 | Microsoft PowerPoint、Apple Keynote、Google Slides | 原生文档模型、模板、母版、手工编辑，PowerPoint 侧是 PPTX/OOXML | 最终文件交付、逐页精修、演示现场、组织模板和人工审阅 | AI 上下文和跨项目资产关系不天然进入平台模型 |
| 办公软件内置 AI | Copilot in PowerPoint、Keynote/Apple Creator Studio 相关能力 | 原生编辑器 + 模板/品牌 + AI 生成/改写 | 在现有办公流程里生成初稿、改写内容、保留组织模板 | 重点仍是当前文件和办公软件生态，资产治理需要外部系统 |
| PowerPoint/Google Slides 插件 | Plus AI、SlidesAI、MagicSlides 等 | 插件侧生成或改写，再写入 Google Slides / PowerPoint / PPTX | 不想离开现有办公软件，但想用 prompt、文档、PDF、URL、视频生成 slides | 能力受插件和宿主 API 限制；跨项目组件化通常较弱 |
| AI-first 演示平台 | Gamma、Beautiful.ai、Canva、Presentations.AI、Decktopus 等 | 专有在线编辑器 + 模板/品牌套件 + AI 大纲/版式/图片 + 导出 | 从空白页快速到可分享 deck，适合提案、课程、营销、轻协作 | 平台内资产强，接入自有 Runtime、代码组件和私有构建链路较弱 |
| Agent + PPT skills | Claude 内置 PowerPoint skill、Codex Presentations skill、团队自定义 deck skill | `SKILL.md` + 代码执行 + PPTX/HTML/图片/渲染 QA 组合 | 高定制 deck、模板跟随、资料抽取、复杂 QA、一次性高质量交付 | skill 管任务流程，不天然管理团队资产、权限和长期引用关系 |
| 通用 Agent skills | OpenAI skills catalog、Claude custom skills、Agent Skills open standard、项目级/个人级/插件级 skills | `SKILL.md` + scripts/references/assets + 按需加载 | 把 PDF、表格、文档、Figma、截图、浏览器、部署等能力封装给 Agent | skills 多了之后需要版本、触发、信任、安全和质量治理 |
| PPTX/OOXML 开发工具 | Open XML SDK、python-pptx、PptxGenJS、Aspose.Slides | 读写 PPTX、shape、text、chart、media、relationships | 需要原生 PPTX、模板继承、批量生产、服务端自动化 | PPTX 结构复杂，视觉还原、动画、图表、母版和兼容性 QA 成本高 |
| HTML slides 框架 | reveal.js、Slidev、Marp | HTML/CSS/JS、Markdown、Vue/Vite、浏览器渲染、PDF/PPTX/SPA 导出 | 技术分享、交互演示、快速预览、代码化版本管理 | 直接导出 PPTX 时对象可编辑性通常不如原生 PPTX |
| 图片生成工具 | `gpt-image-2`、GPT Image、Adobe Firefly、Midjourney、Stable Diffusion | 文生图、图生图、局部编辑、风格化主视觉 | 封面、海报、插画、背景、概念图、营销视觉 | 精确文字、图表、品牌一致性和逐元素编辑需要叠层或后处理 |
| 平台 Runtime | `web-presentation`、自研 Vue/Vite Runtime、截图/构建服务 | 页面源码 + 组件 + 资源 + 主题 + 样式 + 预览/截图/构建 | 长期项目、团队资产复用、多用户隔离、私有化部署 | 比单份文件生成复杂，需要维护平台边界和运行态 |

## Skills 形态补充

skills 不是一种单独的 PPT 产品，而是 Agent 能力的包装方式。调研下来，演示文稿相关 skills 大致有几类：

- **产物生成 skill**：生成 PPTX、HTML deck、PDF、图文卡片或报告页，常见于 Claude 的 PowerPoint/Word/Excel/PDF 内置能力和 Codex 的 Presentations/Documents/Spreadsheets 等 artifact skills。
- **资料处理 skill**：读取 PDF、网页、Word、Excel、Notion、Google Drive、Figma、截图或数据源，为 deck 生成提供事实和素材。
- **设计与品牌 skill**：维护模板规则、品牌色、Logo 使用、Figma 设计系统、图片生成提示词、版式节奏和视觉 QA。
- **渲染与检查 skill**：调用浏览器、Playwright、截图、PPTX 渲染、布局 JSON、contact sheet 或视觉检查流程，避免“文件生成了但页面坏了”。
- **发布与协作 skill**：处理 GitHub、部署、PR、评论、云端存储、导出和交付流程。

这也是为什么 skills 会越来越多：它们分别封装“会做什么”和“怎么稳定地做”。但 skills 本身不是资产平台；如果缺少统一的数据模型和权限边界，多个 skills 之间容易形成彼此分散的工作流。

## 对比总览

| 路径 | 典型产物 | 核心优势 | 常见边界 |
| :--- | :--- | :--- | :--- |
| 传统 Keynote/PowerPoint | `.key`、`.pptx`、PDF、演示现场文件 | 手工控制强、模板和母版成熟、动画/演示体验稳定、团队普遍熟悉 | AI 上下文、跨项目资产关系和运行时能力通常不进入统一模型 |
| 套模板的 AI PPT | 基于模板或品牌套件生成的 PPT/在线 deck | 从 prompt、文档或大纲快速出初稿，能套品牌、改写文案、生成演讲备注和视觉建议 | 多数能力围绕单份 deck 和模板编辑，复杂组件复用、资产依赖和构建链路通常较弱 |
| AI 设计平台 | 在线 deck、网页、图文、PDF、分享链接 | 生成速度快，图库、模板、协作、分享和多格式导出成熟 | 资产主要服务平台自身，和自有代码、私有 Runtime、跨项目构建链路结合有限 |
| Codex/Claude Code + PPT skills | 可编辑 PPTX、HTML deck、脚本化生成物、渲染 QA 产物 | 可把资料抽取、故事线、设计系统、模板跟随、渲染检查和导出写成代理工作流 | 每次交付通常还是任务级产物；权限、资产、引用关系和项目历史需要外部系统承接 |
| 通用内容生成 skills | 文档、表格、PDF、PPT、网页、图像等多类型文件 | 可按领域封装知识、脚本、模板和校验逻辑，适合自动化重复流程 | skills 越多越需要路由、版本、质量门槛和安全治理，否则容易形成分散能力库 |
| `web-presentation` | 平台页面、工作空间组件、资源、主题、样式、截图和构建产物 | 工作空间资产管理、上下文注入、Runtime 预览构建、多用户隔离和私有化部署 | 启动成本高于直接做单份 PPT，不是追求最短路径生成孤立文件 |

## 传统 Keynote/PowerPoint

这一路径的强项是“最终编辑权”。设计师或业务同学可以逐个对象调整文本、图形、图表、动画、过渡、备注和演示方式。Keynote 官方强调主题、幻灯片设置、演示控制、浏览器协作和 iCloud 协作；PowerPoint 生态则在模板、母版、Office 文件互通、企业交付和 Copilot 内置 AI 上持续演进。

适合场景：

- 已有企业模板、母版、动画规范和审阅流程。
- 最终交付必须是 `.pptx` 或 `.key`，且要被多人手工精修。
- 演示现场体验、演讲备注、排练、动画和逐元素控制比平台化资产复用更重要。

主要不足：

- AI 很难天然理解团队跨项目沉淀的资源、组件、主题、样式和引用关系。
- 模板可以规范视觉，但通常不负责管理“这个素材被哪些页面、项目、组件引用”。
- 长期运营一批演示资产时，历史版本、构建产物、预览、权限和复用关系需要额外系统支撑。

## 套模板的 AI PPT

这一类包括内置在办公软件里的 AI，也包括以模板、品牌套件、图库和在线协作为基础的 AI 演示工具。官方资料显示，Microsoft Copilot in PowerPoint 可以从 prompt 或文件创建演示，也强调保留组织模板、品牌颜色、字体和声音；Canva、Gamma、Beautiful.ai 等工具也都在强化“输入主题或资料，生成大纲/初稿，再套品牌和继续编辑”的链路。

适合场景：

- 需要快速从主题、文档、报告或大纲拿到第一版 deck。
- 主要工作是套品牌、改文案、换图、微调版式和导出分享。
- 团队的核心资产是模板、品牌套件、图库和历史 deck。

主要不足：

- AI 上下文多半围绕本次输入、当前文件、模板和品牌套件。
- 页面中的结构、组件和素材不一定成为可编程、可追踪、可跨项目复用的平台对象。
- 当需求从“生成一份 deck”升级为“持续运营一套内容资产和构建链路”时，外部治理成本会上升。

## Codex/Claude Code + PPT Skills

这一路径的重点不是套模板，而是把演示创作变成 agent workflow。OpenAI 的 Codex plugins/skills 用来帮助 Codex 连接工具和执行更具体的工作；Claude 官方也把 skills 描述为扩展 Claude 能力的专门知识与工作流，并列出了 PowerPoint presentation generation 等内置能力。Claude Code skills 还支持项目级、个人级和插件级 skill，`SKILL.md` 可以带说明、引用资料和脚本。

PPT skills 的价值在于“过程可编排”。例如一个高质量 PPT skill 可以要求先抽取资料、写 claim spine、锁定设计系统、生成可编辑 PPTX、渲染预览、检查布局，再导出最终文件。它比纯 prompt 生成更可控，也更适合处理复杂参考资料、模板跟随和 QA。

适合场景：

- 需要一次高质量、强定制的 PPT、HTML deck 或报告页。
- 要把研究、数据、素材、排版、渲染和 QA 都纳入同一次代理执行。
- 团队愿意维护 skill，使它持续吸收最佳实践、模板规则和质量门槛。

主要不足：

- skill 解决的是“代理如何完成某类任务”，不天然解决“团队资产如何被长期建模、复用和治理”。
- 产物常常仍是任务级文件；跨项目组件、资源引用、主题继承、页面关系和构建产物需要额外系统维护。
- skills 数量增加后，需要管理命名、版本、触发条件、权限、安全和质量，否则会从能力库变成分散脚本库。

## AI 创作的技术路线

同样叫“AI 做 PPT”，底层路线可能完全不同。路线不同，决定了产物能不能编辑、视觉能不能稳定复现、能不能接入团队资产，也决定了后续维护成本。

| 技术路线 | 代表产品 / skills / 工具 | 典型产物 | 主要优势 | 主要边界 | 与 `web-presentation` 的关系 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 直接改 PPTX/OOXML | Open XML SDK、lxml、python-pptx 的底层 XML 扩展、Agent 直接 patch `.pptx` 包 | 原生 `.pptx` | 可保留既有模板、母版、占位符、关系文件和部分复杂对象 | OOXML 结构复杂，关系、布局、主题、图表、媒体和兼容性容易破坏；AI 直接改 XML 需要强 QA | 可作为未来 PPTX 导入/导出或模板跟随能力，但不适合作为平台页面的唯一表达 |
| PPTX SDK / DSL 生成 | PptxGenJS、python-pptx、Aspose.Slides、artifact-tool presentation JSX、团队自定义 PPT skill | 可编辑 `.pptx` | 比裸写 XML 更稳定，适合批量生成、模板填充、图表/表格/文本自动化 | 受库能力限制，不一定覆盖所有 PowerPoint 动画、母版、图表和效果；视觉 QA 仍必要 | 适合作为构建出口之一，把平台页面或项目数据导出到 PPTX |
| Office 插件生成 | Copilot in PowerPoint、Plus AI、SlidesAI、MagicSlides | 宿主内可编辑 slides、PPTX、Google Slides | 用户不离开原有办公软件，生成后可继续手工编辑 | 依赖宿主 API 和插件生态；平台外资产、组件和上下文难以统一治理 | 适合作为外部对照或导出后精修路径，不适合作为平台内部模型 |
| HTML / 前端生成 | reveal.js、Slidev、Marp、Vue/Vite、React、自研 Runtime | HTML deck、SPA、PDF、PNG、部分 PPTX | LLM 易写易改，浏览器预览快，动效、响应式、数据可视化和交互能力强 | 转 PPTX 时对象可编辑性弱，复杂 CSS 与打印/截图一致性需要 QA | 是 `web-presentation` 的核心方向之一，Runtime 可以承载预览、截图和构建 |
| Markdown 到 slides | Marp、Slidev、Reveal Markdown、Agent 生成 markdown deck | Markdown、HTML、PDF、PPTX | 内容优先、版本管理友好、生成速度快，适合技术分享和结构化讲义 | 高定制视觉通常需要 CSS/组件；复杂商业 deck 容易模板化 | 可作为页面源码或样式库的轻量输入形态，但需要平台组件和主题约束 |
| 图片生成整页 | `gpt-image-2`、GPT Image、Adobe Firefly、Midjourney、Stable Diffusion | PNG/WebP/JPEG、整页视觉、插画、背景 | 第一眼视觉冲击力强，适合封面、海报、插画、概念图和营销视觉 | 文本、图表、精确布局、品牌一致性和可编辑性弱；全页图片后续难维护 | 适合作为资源库素材、封面主视觉或背景，不应替代结构化页面模型 |
| 图片 + 可编辑叠层 | 图片模型生成背景，HTML/PPTX 叠加标题、正文、图表、Logo 和页码 | 可视强、局部可编辑的页面或 PPTX | 兼顾视觉表现和文字/图表可控，适合营销页、封面、图文卡片 | 需要管理版权、品牌来源、裁切比例、遮挡、多页一致性和替换策略 | 很适合平台资源库 + 页面源码组合：图片是资源，文字/图表是结构 |
| HTML 截图进 PPTX | Playwright/Puppeteer/浏览器截图，或 HTML/PDF 再插入 PPTX | 视觉稳定的 PPTX/PDF/PNG | 视觉还原稳定，适合复杂前端视觉和短期交付 | PPTX 内多为图片，编辑性、可访问性和对象级复用较差 | 可作为截图预览、快照构建或非编辑型交付出口 |
| 多 Agent / 多 skill 流程 | 资料抽取 skill、图像 skill、PPT skill、浏览器 QA skill、发布 skill 串联 | 研究笔记、deck、图片、截图、发布产物 | 可把“调研-故事线-设计-生成-验证-交付”拆成专业步骤 | 协调成本高，容易出现上下文漂移、重复素材和质量责任不清 | 平台可以提供统一上下文、工具权限和资产边界，降低多 skill 漂移 |
| 平台 Runtime 生成 | `web-presentation`、自研 Vue/Vite Runtime、预览/截图/构建服务 | 平台页面、组件、资源、主题、样式、截图、构建产物 | 能把 AI 创作、资产复用、运行态验证和团队治理串起来 | 需要维护平台、数据模型、Runtime 边界、权限和部署链路 | 是长期资产治理的主线，可吸收 PPTX、HTML、图片和 skill 能力作为子能力 |

### 技术路线的取舍

如果重点是“最终文件必须在 PowerPoint 里继续精修”，优先考虑 OOXML/PPTX 原生路线、PPTX SDK 或 Office 插件路线。它们牺牲一部分前端表达力，换来更强的对象可编辑性和办公软件兼容。

如果重点是“AI 能快速迭代结构、视觉和动效”，HTML/前端路线更自然。代码、样式、组件和浏览器渲染都更适合 LLM 修改，也更容易接入自动截图和视觉 QA。

如果重点是“第一眼视觉冲击力”，图片生成路线很有价值。OpenAI 官方模型名是 `gpt-image-2`，这类模型适合生成或编辑高质量视觉，但官方图像生成文档也明确提到，图像模型在精确文本、长期一致性和结构化构图控制上仍有局限。因此它更适合作为主视觉、背景、插画或素材来源，而不是直接承载大量可编辑文字和图表。

如果重点是“团队长期生产和复用”，单一技术路线不够。`web-presentation` 更偏混合式：页面源码和组件源码用前端 Runtime 承载，资源、主题和样式由 Backend 建模，AI 通过工具和上下文注入工作。它可以在必要时吸收图片生成、HTML 生成、截图、构建和未来 PPTX 导出能力，但核心仍是平台对象和资产关系。

### 技术路线与产品形态的常见组合

| 产品 / skill 形态 | 常见组合 |
| :--- | :--- |
| Copilot in PowerPoint | PowerPoint 原生编辑器 + 组织模板/Brand kit + AI 生成/改写 |
| Plus AI / SlidesAI / MagicSlides | Google Slides 或 PowerPoint 插件 + prompt/文档/PDF/URL 输入 + PPTX/Slides 输出 |
| Gamma / Canva / Beautiful.ai / Presentations.AI | 在线编辑器 + 模板/品牌套件 + AI 大纲/设计/图片 + 链接/PDF/PPTX 导出 |
| Codex/Claude Code + PPT skill | `SKILL.md` + 资料读取 + PPTX SDK/HTML/图片生成 + 渲染 QA + 文件导出 |
| Slidev / Marp / reveal.js | Markdown/HTML/Vue + 浏览器预览 + PDF/PNG/PPTX/SPA 导出 |
| `web-presentation` | 平台数据模型 + Vue/Vite Runtime + 资源/组件/主题/样式 + AI 工具 + 截图/构建 |

## `web-presentation`

`web-presentation` 的切入点是平台模型，而不是某一种最终文件格式。它把演示文稿、图文卡片、专题报告页、数据解读页等内容形态拆成页面、资源、组件、主题、样式和构建产物，并通过 Backend、Editor、Runtime 和 AI Agent 协同。

它的差异主要体现在四点：

- **上下文稳定**：AI 看到的不只是 prompt，而是经过 Backend 组织和校验的工作空间、项目、页面、资源、组件、主题、样式和工具约束。
- **资产可复用**：素材、组件、主题、字体和样式是工作空间对象，可被多个项目、页面和 AI 会话持续引用。
- **运行态可验证**：页面源码、组件源码和 previewSchema 经 Backend 边界校验后进入 Runtime，用户可以在 Editor 中预览、截图、诊断和构建。
- **治理可扩展**：多用户隔离、工作空间权限、工具确认、构建产物托管和私有化部署是平台能力的一部分。

适合场景：

- 团队要长期生产同一品牌、同一业务线或同一内容体系下的视觉内容。
- 需要 AI 每次创作都理解当前项目、页面、组件、资源和样式边界。
- 需要把资源库、组件库、主题库、样式库和构建链路沉淀下来，而不是每次从单份文件重新开始。
- 需要在自有环境中部署，控制业务数据、模型凭证、权限和产物发布流程。

主要不足：

- 对“今天就要一份 PPTX 初稿”的需求，传统 AI PPT 或 PPT skill 通常更快。
- 对完全依赖 PowerPoint 动画、母版和逐元素精修的团队，原生 PPTX 仍然是最终编辑主战场。
- 平台化路线需要维护 Backend、Editor、Runtime、数据模型和权限边界，初始复杂度更高。

## 怎么选择

| 需求 | 更适合的路径 |
| :--- | :--- |
| 最终交付必须由业务团队在 PowerPoint 或 Keynote 里精修 | 传统 Keynote/PowerPoint |
| 需要快速把主题、文档或大纲变成第一版 PPT | 套模板的 AI PPT |
| 需要结合模板、品牌套件、图库、协作和分享 | AI 设计平台或 Copilot in PowerPoint |
| 需要一次高质量、强定制、带资料抽取和渲染 QA 的 deck | Codex/Claude Code + PPT skills |
| 需要保留 PowerPoint 对象级编辑能力 | OOXML/PPTX 原生或代码生成 PPTX 路线 |
| 需要浏览器级视觉、动效、响应式和快速预览 | HTML/前端生成路线 |
| 需要封面、插画、海报感页面或强视觉背景 | `gpt-image-2` 等图片生成路线，配合可编辑文字叠层 |
| 需要把多类办公产物自动化，如 PPT、文档、表格、PDF | 通用内容生成 skills |
| 需要跨项目沉淀资源、组件、主题和样式 | `web-presentation` |
| 需要 AI 持续理解项目上下文和工作空间资产 | `web-presentation` |
| 需要私有化部署、多用户隔离和构建产物托管 | `web-presentation` |

## 如何理解平台定位

这些路线之间不是互斥关系。传统 PowerPoint、Keynote 和 Google Slides 适合作为最终编辑与演示工具；AI PPT 产品适合快速生成初稿；PPT skills 适合把一次复杂交付做成可执行流程；HTML、PPTX SDK 和图片生成则是不同的底层实现方式。

`web-presentation` 的定位更靠后：它关注的是团队如何长期管理演示文稿相关资产。页面、组件、资源、主题、样式、AI Agent、预览和构建都进入统一平台模型后，AI 才能持续获得稳定上下文，团队也才能持续复用和治理这些内容。

因此，`web-presentation` 不是要替代 Keynote、PowerPoint、AI PPT 工具或 PPT skills，而是补足它们在长期项目、团队资产、运行时能力、权限隔离和私有化交付上的系统边界。


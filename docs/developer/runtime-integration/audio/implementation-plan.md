# 音频实施计划

状态：待实施。字段和行为以[统一契约](./contract.md)为准，本页只定义模块落点、阶段顺序和交付边界。

## 1. 实施策略

按“资源先可治理、旁白再进入播放生命周期、短音效最后接 shell”的顺序推进：

1. M0 先让 `audio` 成为完整资源类型并交付 `AssetAudio.v1` 的手动内容播放。
2. M1 复用现有 `PageMediaSession` 和 `usePlaybackHost`，增加旁白用途，不另建第二套页面媒体调度器。
3. M2 才增加项目 cue 存储、shell 引擎和公开 `useAudioCue.v1`，避免 cue 配置早于资源/快照能力落地。

每个阶段出口都要求实际浏览器和独立构建产物证据。只在 jsdom 中模拟 `HTMLMediaElement.play()` 不能替代自动播放受阻、Range、格式兼容和双窗口播放者验证。

## 2. Backend

### 2.1 音频资源

主要入口：

- `backend/app/models/enums.py`
- `backend/app/schemas/asset.py`
- `backend/app/services/asset_service.py`
- `backend/app/services/resource_reference_parser.py`
- 资源 API、External API、包服务和 OpenAPI 生成链

实施要求：

- 新增 `audio` 枚举、角色、扩展名/MIME 校验和错误用例，不把音频伪装为 `video`。
- 保持二进制资源不可文本编辑；不进入图片渲染比例分析或回填任务。
- 复核受保护文件读取的 `HEAD`、Range、缓存和 Content-Type；不为音频恢复 public fallback。
- 通用 `Asset* name` 解析应自动覆盖 `AssetAudio`，另补静态属性校验：purpose、volume、playbackRate、narration+loop 和多旁白。
- cue 绑定采用明确关系表，归档/删除资产前进入引用摘要；项目 cue 查询不得解析任意页面源码猜测。

### 2.2 项目设置与快照

- 为 `Project.audio_settings_json` 增加严格 DTO、默认值和双库迁移。
- 新增 `ProjectAudioCueBinding`；同项目 cue key 唯一，资产必须同工作空间、active、type=audio。
- 项目 API、External API、模板包和 AI 工具区分省略、完整替换及显式清空，避免旧客户端覆盖。
- preview artifact/build job 创建时固化音量、cue 的资源逻辑名和 hash；后续修改不改变旧快照。
- `ProjectArtifactBuilder` 主动收集 cue 绑定资产；包导入按逻辑名重建 ID，冲突和整个事务失败沿用现有包语义。

### 2.3 AI 能力

- 先更新 `backend/app/ai/tool_specs.py`，再派生查询/写工具说明。
- AI 创建旁白页面时使用 `AssetAudio.v1 purpose="narration"`，不写原生远程 URL、不生成 autoplay。
- 查询资源时披露音频类型和推荐用途；项目 cue 写入只有在对应执行器和 API 已落地后才能披露。
- 不在本计划加入音频生成、配音供应商或永久删除工具。

## 3. Editor

主要入口：

- `editor/src/components/project/asset-manager.ts`
- `editor/src/views/asset-view-options.ts`
- `AssetsView`、`AssetManagerPanel`、`AssetPreviewFrame`
- 项目展示配置对话框和生成 API 类型

实施要求：

- 新增音频过滤、上传、替换、试听、历史和引用展示；试听永不自动开始。
- 显示文件类型、大小、可读取时长和格式提示；首版不生成波形。
- `audio` 不进入内容文本编辑、比例回填或图片背景控件。
- M1 提供旁白 authoring 提示和放映警告；若能取得 duration 且 timer 短于旁白，提示改用 `media_end`。
- M2 在项目展示配置中增加“音频”分区：三段音量、前进/后退 cue、语义 cue 绑定、试听和清空。
- UI 遵循 `DESIGN.md`；选择器只列当前工作空间 active audio，保存时仍由 Backend 最终校验。

## 4. Runtime Kit

主要入口：

- `runtime/src/runtime-kit/public/components/assets/`
- `runtime/src/runtime-kit/internal/renderers/`
- `runtime/src/runtime-kit/public/composables/`
- `runtime/src/runtime-kit/manifest/runtime-kit.manifest.json`

实施要求：

- 新增 `AssetAudio.v1.vue` 与内部 AudioViewer，沿用 `useAssetSrc.v1`，输出稳定 media purpose/导出标记。
- `AssetRenderer` 支持 `render_type=audio`；资源预览显式 controls，旁白预览不自动播放。
- manifest 提供参数 Schema、用法、约束和 AI 示例；Backend 代码检查与公开清单同步。
- 新增 `useAudioCue.v1` 时只暴露语义 key；未注入服务时稳定 no-op，不导出 shell 内部引擎。

## 5. Runtime shell

### 5.1 页面旁白

主要入口：

- `runtime/src/core/media/page-media-session.ts`
- `runtime/src/runtime-shell/playback/usePlaybackHost.ts`
- `runtime/src/runtime-shell/transitions/PageTransitionHost.vue`
- `runtime/src/runtime-shell/transitions/RuntimePageStage.vue`

实施要求：

- 媒体 session 为每个稳定放映页建立，而不只在 `media_end` 建立；是否自动播放由目的和推进模式决定。
- 收集 target 的 purpose、loop、播放状态和错误；content 与 narration 使用同一事件源和 generation 围栏。
- 旁白等待 transition settled 与 render-ready；离页清理、暂停恢复和 visibility/freeze 使用现有宿主生命周期。
- `media_end` 保持“所有参与媒体结束”语义；多旁白、解码失败和 autoplay blocked 进入可观测状态。
- 演讲者模式仅 audience 的 `usePlaybackHost` 建立可播放 session，console 不创建媒体或 cue 引擎。

### 5.2 Cue 引擎

- `AudioCueEngine` 归 Runtime shell 内部，不进入 Runtime Kit 公开组件目录。
- 由 shell 读取 artifact audio config、解析资源 URL、维护 transition 单通道和 interaction 池。
- `PageTransitionHost` 新增 typed `started` 事件；只对被接受的真实 navigation generation 播放。
- 把 cue 服务通过 injection key 提供给 `useAudioCue.v1`，执行上下文不允许时提供 no-op provider。
- Playback 控制条与键盘表增加全局静音；全屏退出、隐藏、freeze、卸载和双窗口角色变化均清理状态。

## 6. Renderer 与导出

- `execution-policy` 明确 audio autoplay/cue 均为 false；静态路径不创建 AudioCueEngine。
- Renderer 截图不能等待音频 duration 或 `ended`，也不因音频请求失败使截图失败。
- `AssetAudio` 在 PDF/PPTX/print 中不播放；有 controls 的可视 UI 按静态媒体规则省略或输出小型占位，行为需固定并测试。
- PPTX 导出报告记录 audio omitted；本计划不增加 OOXML 媒体嵌入。
- 远程 Renderer 浏览器不得取得 Backend 服务票据；音频资源读取仍绑定 artifact P，静态上下文尽量 `preload=none`。

## 7. CLI 与 MCP

- 主仓 External API 先交付 `audio` 上传/查询/替换与项目 audio settings/cue binding 契约、幂等和 capability。
- `web-presentation-cli` 增加 `--type audio`、项目音频配置读写和帮助；保留旧版本对未知字段的安全行为。
- `web-presentation-mcp` 增加对应异步客户端与工具 Schema；工具返回资产 ID、逻辑名和绑定摘要，不返回私有持久 URL。
- 两个独立仓分别测试和版本发布，主仓通过不等于外部消费者已完成。

## 8. 阶段与提交顺序

| 阶段 | 建议顺序 | 出口 |
| :--- | :--- | :--- |
| M0 | WP01 → WP02 →（WP03、WP04）→ WP05 → WP06 | `audio` 资源和手动 `AssetAudio.v1` 可发布 |
| M1 | WP07 → WP08 → WP09 →（WP10、WP11）→ WP12 | 页面旁白、静音、双窗口与 media_end 可发布 |
| M2 | WP13 → WP14 → WP15 →（WP16、WP17、WP18、WP19）→ WP20 | 切页/点击 cue 与所有配置入口可发布 |

完整前置和提交边界见[工作包清单](./work-packages/README.md)。不同工作包修改同一热点文件时遵循上述依赖串行合并，尤其是 `usePlaybackHost.ts`、Runtime Kit manifest、项目 API DTO 和 Editor 项目配置对话框。

## 9. 发布与回滚

- Backend 必须先能安全保存并下发新字段，Runtime 能力位就绪后 Editor 才显示入口。
- 历史项目迁移默认无 cue，升级后不得产生声音；回滚旧 Runtime 时 Backend 不应向其宣称 cue 可用。
- 音频播放异常不得阻塞手动导航；只有 `media_end` 的参与媒体错误使用已有超时/重试/下一页/停止恢复界面。
- 关闭 M1/M2 能力开关不删除资源和绑定；重新启用后配置仍在。
- 不用删除数据作为回滚手段。需要修改持久化 Schema 时提供 downgrade 或明确的前向兼容策略。

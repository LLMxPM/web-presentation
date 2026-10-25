# 音频统一契约

状态：v1 基线已冻结（WP01，2026-10-18）；后续实现不得另建默认值或 cue key 规则。本文是音频字段、默认值、引用方式和运行语义的单一事实源。

## 1. 资源类型

Backend 新增 `AssetType.AUDIO = "audio"`。数据库现有 `WorkspaceAsset.asset_type` 为字符串列，不为增加枚举值单独修改列类型；所有 API、生成类型、过滤器和资源角色解析必须同步。

首版允许文件：

| 扩展名 | 接受 MIME | 说明 |
| :--- | :--- | :--- |
| `.mp3` | `audio/mpeg` | 推荐的跨浏览器交付格式 |
| `.m4a` | `audio/mp4`、`audio/x-m4a` | 容器与浏览器支持需实机验收 |
| `.aac` | `audio/aac` | 原始 AAC；不保证所有浏览器一致 |
| `.ogg` | `audio/ogg` | 编码兼容性由浏览器决定 |
| `.wav` | `audio/wav`、`audio/x-wav` | 适合短音效，不建议长旁白 |

扩展名和 MIME 必须同时落在允许范围；`application/octet-stream` 不作为常规绕过入口。平台首版不转码，因此资源详情和上传提示必须说明推荐 MP3，并在真实 Chromium/Firefox/WebKit 验收矩阵中记录格式结果。FLAC、无损母带和工程源文件不在首版可播放格式内。

音频属于 `AssetRole.CONTENT`，不可文本编辑，不参与图片宽高比例回填。上传、替换、历史、复制、归档、恢复、原始下载、引用保护和权限边界与其它二进制内容资源一致。

## 2. `AssetAudio.v1`

公开路径固定为：

```ts
import AssetAudio from '@runtime-kit/public/components/assets/AssetAudio.v1.vue'
```

首版属性：

```ts
type AssetAudioPurpose = 'content' | 'narration'
type AssetAudioPreload = 'none' | 'metadata' | 'auto'

interface AssetAudioProps {
  name: string
  purpose?: AssetAudioPurpose
  controls?: boolean
  volume?: number
  playbackRate?: number
  preload?: AssetAudioPreload
  loop?: boolean
  fallback?: string
}
```

默认值与约束：

| 字段 | 默认 | 约束 |
| :--- | :--- | :--- |
| `purpose` | `content` | 只允许 `content`、`narration` |
| `controls` | `content` 为 `true`，`narration` 为 `false` | 可显式覆盖，但旁白不建议显示控件 |
| `volume` | `1` | 有限数，范围 `0–1` |
| `playbackRate` | `1` | 有限数，范围 `0.5–2` |
| `preload` | `metadata` | 静态执行上下文强制降为 `none` |
| `loop` | `false` | `narration` 禁止 `loop=true` |
| `fallback` | 空 | 只作缺失资源兼容；页面不应把远程 URL 当正式资产 |

组件内部输出原生 `<audio>`，并声明稳定的宿主契约：

```html
<audio
  data-runtime-media-target="audio"
  data-runtime-media-purpose="narration"
></audio>
```

`AssetAudio.v1` 不暴露 `autoplay`。自动播放资格由 `purpose`、execution policy 和放映宿主共同决定，避免页面绕过静态禁播与浏览器恢复流程。一个实际渲染页面最多一个 `purpose="narration"` 目标；代码检查对静态可见冲突报错，Runtime 对动态冲突进入有界错误状态，不允许多段旁白同时说话。

普通内容音频示例：

```vue
<AssetAudio name="customer-interview" purpose="content" controls />
```

页面旁白示例：

```vue
<AssetAudio name="chapter-01-narration" purpose="narration" :volume="0.9" />
```

## 3. 页面媒体语义

`PageMediaSession` 收集当前稳定页面中的原生 `audio, video`，并读取 `data-runtime-media-purpose`。未声明 purpose 的现有媒体按 `content` 兼容。

### 3.1 内容音频

- 手动页不会因为存在 content 音频而自动播放；用户通过控件或页面业务操作播放。
- `advance.mode=media_end` 时，所有非循环、可参与的 content 媒体继续沿用现有媒体集合语义。
- `loop=true` 的 content 音频参与暂停、恢复和离页清理，但不参与完成判定。

### 3.2 页面旁白

- 只在真实放映执行上下文自动启动；普通交互预览必须先由用户显式试听或进入放映。
- 开始条件为：当前 route generation 仍有效、整页过渡已 `settled`、页面 render-ready 已完成、播放状态允许媒体。
- `advance.mode=manual`：旁白自动播放，但结束不翻页。
- `advance.mode=timer`：计时与旁白并行；计时到达时正常翻页并停止旁白。Editor 对明显短于已知音频时长的配置给出警告，不静默改写为 `media_end`。
- `advance.mode=media_end`：旁白与其它参与媒体纳入同一完成集合，全部结束后翻页；无参与媒体时仍按现有 `delay_ms` 回退。
- 暂停放映、页面隐藏或 freeze 时暂停；只有本会话记录为正在播放的旁白才在恢复时继续。
- 离开页面、generation 作废或宿主卸载时立即暂停、归零并释放监听；返回页面从头播放，不跨页续播。
- 浏览器拒绝 `play()` 时进入现有 blocked 状态，等待用户手势重试；解码或网络错误使用现有媒体错误链路。

## 4. 项目音量和 cue 绑定

M2 新增项目级音频设置，存储中把音量设置与资源绑定分开：

- `Project.audio_settings_json` 只保存无资源引用的严格设置。
- `ProjectAudioCueBinding` 保存 `project_id + cue_key + asset_id + gain_percent`，建立数据库外键和唯一约束。

项目设置 API 结构：

```json
{
  "master_volume_percent": 100,
  "narration_volume_percent": 100,
  "effects_volume_percent": 30,
  "cue_bindings": [
    {
      "key": "transition.forward",
      "asset_id": 51,
      "gain_percent": 100
    },
    {
      "key": "interaction.confirm",
      "asset_id": 52,
      "gain_percent": 80
    }
  ]
}
```

所有百分比为严格整数 `0–100`。最终有效增益：

```text
旁白 = master × narration × AssetAudio.volume
音效 = master × effects × binding.gain
```

Applier 位置：旁白由 `AudioViewer` 在设置原生 `volume` 时叠加项目快照；cue 由 `AudioCueEngine` 在播放时计算。两者都不向页面暴露音量入口。

Runtime 会话静音不写回项目配置，初始为未静音；用户可通过控制条和 `M` 快捷键切换。项目没有绑定 cue 时完全静默，不内置默认音效文件。

cue key 规则为小写点分段：`^[a-z][a-z0-9_-]*(\.[a-z0-9_-]+)+$`，最大 80 字符。系统保留：

- `transition.forward`
- `transition.backward`
- `interaction.confirm`
- `interaction.cancel`
- `interaction.error`
- `interaction.select`

允许项目增加其它 `interaction.*` key；首版拒绝未知的系统命名空间。绑定资产必须属于项目所在工作空间、状态可用且类型为 `audio`。项目归档不级联归档资产；资产归档/删除前引用检查必须显示项目 cue 绑定。

清空绑定使用原子入口 `POST /api/v1/projects/{project_id}/audio-cues/clear`：单事务只删除绑定，不读出并重写音量，因此保留三段当前值并避免覆盖并发音量更新。能力关闭时仍允许清空历史绑定，但不允许新增或恢复绑定；完整音量更新仍需显式提交完整 `audio_settings` 对象，不隐含在 clear 中。

自 2026-10-25 起，`slideshow.audio` 的 `audio_assets`、`page_narration`、`audio_cues` 均默认返回 `true`；以下关闭语义适用于能力集合被显式收窄的环境与回归测试。能力门禁与写入一致：

- `audio_cues=false` 时，项目创建、项目更新、configuration 更新和模板导入只要携带非空 `cue_bindings` 就返回 422 `AUDIO_CAPABILITY_UNAVAILABLE`；音量更新与空 `cue_bindings` 继续允许。
- `page_narration=false` 时，页面与组件保存拒绝可静态判定的 `purpose="narration"`；`audio_cues=false` 时拒绝可静态识别的 `useAudioCue` 调用（含别名导入）。`validate` 返回 `valid=false` 与同一业务码，真正写入仍独立校验。
- 检查指纹包含当前开放能力集合，能力开关变化后不复用旧 `valid` 缓存。
- 新 preview/build 快照在 `audio_cues=false` 时不携带 cue；已生成 artifact 与旧 Runtime 版本不因开关变化自动失效，也不承诺 capability 是全局紧急停声开关。

## 5. Runtime artifact 结构

Backend 在创建 preview artifact 或 build job 时把数据库绑定解析为不可变快照：

```json
{
  "audio": {
    "volume": {
      "master": 1,
      "narration": 1,
      "effects": 0.3
    },
    "cues": {
      "transition.forward": {
        "assetName": "page-whoosh",
        "gain": 1
      },
      "interaction.confirm": {
        "assetName": "confirm-soft",
        "gain": 0.8
      }
    }
  }
}
```

Runtime 不接收 `asset_id`，也不接收带票据的固定 URL；它通过当前 artifact 的 `assets` 映射按 `assetName` 解析。快照创建后即使项目配置或资源名称发生变化，旧 artifact/build 仍使用创建时固化的映射和文件 hash。

项目 cue 资产必须由 `ProjectArtifactBuilder` 主动加入资源集合，因为它们不一定出现在页面源码中。模板包导出使用逻辑资源名和文件内容表达绑定，导入时在目标工作空间解析/创建资产并重建 ID 绑定。

## 6. `AudioCueEngine` 与 `useAudioCue.v1`

Runtime shell 创建一个项目级 `AudioCueEngine`，首版使用 `HTMLAudioElement`：

- transition channel 只有一个实例；新切页 cue 立即停止并归零前一个 cue。
- interaction channel 使用最多 4 个实例的小型池；池满时丢弃最旧的非关键播放，不无限创建元素。
- 同一 key 默认 80ms 节流；缺失绑定、静态上下文、静音或加载失败均返回 no-op，不阻塞业务动作。
- 常用短 cue 可 `preload=auto`；旁白只预取当前页与下一页 metadata，不全量预载。
- `visibilitychange`、freeze、页面卸载和会话结束时暂停并释放；恢复不自动补播已经错过的短 cue。

页面源码只使用公开 composable：

```ts
import { useAudioCue } from '@runtime-kit/public/composables/audio/useAudioCue.v1'

const { playCue } = useAudioCue()

function confirm(): void {
  playCue('interaction.confirm')
  submit()
}
```

返回值只表达 `played | skipped | unavailable` 等同步可观察状态，页面不得依赖 cue 播放完成推进业务。composable 通过 Runtime 注入服务工作；组件预览、捕获、导出和未提供 shell 的上下文返回稳定 no-op。公开 API 只接受合法 `interaction.*` key；`transition.forward` / `transition.backward` 由 shell 切页单通道独占，页面调用返回 `unavailable`。

## 7. 切页音效触发

`PageTransitionHost.show()` 在接受一个真实、不同页面的新 generation 时发出 `started`：

```ts
interface PageTransitionStartedEvent {
  generation: number
  fromPath: string | null
  toPath: string
  direction: 1 | -1
  effect: 'none' | 'fade' | 'push'
}
```

- 初次挂载、相同路径刷新、被合并掉的中间导航和旧 generation 不发声。
- `direction=1` 播放 `transition.forward`，`direction=-1` 播放 `transition.backward`。
- 视觉效果为 `none` 仍属于真实翻页，可以播放 cue。
- 点击了“下一页”但最终未形成页面变化时不播放。
- 导航按钮若已触发 transition cue，默认不再额外播放 `interaction.select`，避免双声。

## 8. 执行上下文与导出

| 上下文 | 内容音频 | 页面旁白 | cue |
| :--- | :--- | :--- | :--- |
| 实际全屏放映 | 用户控制 | 自动 | 允许 |
| 演讲者观众窗口 | 用户控制 | 自动 | 允许 |
| 演讲者控制台 | 不播放 | 不播放 | 不播放 |
| 普通交互预览 | 用户手势试听 | 不自动 | 仅用户显式试听工具 |
| 组件/资源预览 | 用户手势试听 | 不自动 | 不播放 |
| thumbnail/capture/check | 不加载或不播放 | 不播放 | no-op |
| PDF/PPTX/print | 不播放；首版省略音频 | 不播放；首版省略音频 | no-op |

`AssetAudio.v1` 使用 `data-runtime-kit-media="v1"` 和 `data-runtime-kit-media-kind="audio"` 标记导出边界。静态导出可在报告中记录“音频已省略”，但不得等待播放、生成空白大框或把临时票据写入产物。

## 9. 兼容与版本

- 没有 `audio_settings_json` 的历史项目读取为默认音量且无 cue 绑定，因此行为完全静默。
- Runtime 未声明音频能力时，Backend/Editor 不开放旁白或 cue 配置；`AssetAudio.v1` 依赖 manifest 版本化能力。
- 旧客户端省略 audio 设置时，项目更新不得清空现有 cue；显式 `null`、空列表和省略必须在 API 契约中区分。
- `AssetAudio.v1` 一旦发布不做破坏性修改；未来不兼容演进新增 `AssetAudio.v2`。
- 跨页 BGM 若未来立项，应新增独立 ambient channel 和会话模型，不复用 narration 的页面 DOM 生命周期。

/**
 * 文件功能：维护 AI E2E 用例与 Backend mock 场景之间的契约：场景 ID、固定自然语言输入与用户可见期望。
 *
 * 依据 docs/developer/testing/e2e-redesign.md §3.3：本文件只保存场景 ID、用户输入和用户可见期望，
 * 不承载 Backend 响应脚本；场景执行逻辑全部收敛在 backend/app/ai/testing/。
 */

/** seed 播种的内容助手 mock 模型配置名；AI 用例必须显式选中它，不依赖面板默认模型。 */
export const AGENT_MOCK_CONFIG_NAME = 'Smoke E2E Mock Agent'

/** 内容助手普通对话场景：initial → final_text。 */
export const AGENT_HELLO_CASE = {
  scenarioId: 'e2e-agent-hello',
  input: '你好，我是 E2E mock 普通对话用例，请用一句话自我介绍。',
  finalText: '你好，我是内容助手的 E2E mock 响应，用于验证真实会话链路。',
} as const

/** 内容助手视觉链路场景：analyze_visuals → generate_image → deferred 恢复 → final_text。 */
export const AGENT_VISUAL_CASE = {
  scenarioId: 'e2e-agent-visual-link',
  input: '请先分析这张参考图，然后基于它生成一张配图并保存到资源库。',
  finalExpectation: '配图已生成并保存到资源库',
  assetNamePrefix: 'e2e-mock-visual',
} as const

/** 页面重资源写入场景：list_entities → create_entity → external job → 父 Run 续跑。 */
export const AGENT_PAGE_EXTERNAL_CASE = {
  scenarioId: 'e2e-agent-page-external',
  input: '请在当前项目创建一页 E2E external job 验证页。',
  finalText: '页面 external job 已完成并恢复父运行。',
  pageTitle: 'E2E External Job Page',
} as const

/**
 * 视觉用例上传的参考图：1x1 合法 PNG 的 base64 内容。
 * 断言只关注真实保存与展示链路，不做像素级比较。
 */
export const VISUAL_REFERENCE_PNG_BASE64
  = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgAAAAAgAB4iG8MwAAAABJRU5ErkJggg=='

/** 构造参考图上传参数，供 setInputFiles 使用。 */
export function buildReferenceImage(name: string) {
  return {
    name,
    mimeType: 'image/png',
    buffer: Buffer.from(VISUAL_REFERENCE_PNG_BASE64, 'base64'),
  }
}

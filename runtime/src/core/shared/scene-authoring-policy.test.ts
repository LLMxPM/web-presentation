/** 文件功能：对拍 Backend 的 Scene 导入边界，并执行构建和诊断实际使用的生成插件。 */
import { describe, expect, it } from 'vitest'
import cases from '../../../../tests/fixtures/scene-import-policy-cases.json'
import { isForbiddenSceneImport } from './scene-authoring-policy'
import { createRuntimeKitImportGatePluginSource } from '../plugins/runtime-build-worker'

describe('Scene 源码导入策略', () => {
  it.each(cases)('$source 的拦截结果为 $forbidden', ({ source, forbidden }) => {
    expect(isForbiddenSceneImport(source)).toBe(forbidden)
  })

  it('生成插件限制页面和组件，不拦截平台 GSAP 实现；SFC 查询后缀不绕过规则', async () => {
    const allowed = '@runtime-kit/public/composables/motion/usePageScene.v1'
    const factory = new Function(`${createRuntimeKitImportGatePluginSource()}; return createRuntimeKitImportGatePlugin`)()
    const plugin = factory([allowed], '/tmp')
    for (const importer of ['/tmp/src/views/Page.vue?vue&type=script', 'C:\\tmp\\src\\workspace-components\\C1\\v\\1.vue']) {
      for (const { source, forbidden } of cases) {
        if (forbidden) await expect(plugin.resolveId(source, importer)).rejects.toMatchObject({ code: 'SCENE_GSAP_IMPORT_FORBIDDEN' })
        else await expect(plugin.resolveId(source, importer)).resolves.toBeNull()
      }
    }
    await expect(plugin.resolveId('gsap', '/tmp/src/core/scene/gsap-scene-task.ts')).resolves.toBeNull()
    await expect(plugin.resolveId('gsap', undefined)).resolves.toBeNull()
    await expect(plugin.resolveId('@runtime-kit/internal/secret', '/tmp/src/views/Page.vue')).rejects.toMatchObject({ code: 'RUNTIME_LOCAL_IMPORT_FORBIDDEN' })
  })
})

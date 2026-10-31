/**
 * 文件功能：记录观众窗口多屏能力（window.getScreenDetails）在当前机器上的真实授权与屏幕数量。
 *
 * 单显示器环境无法验证「跨屏全屏」；本用例只如实登记结果，不把当前窗口全屏回退当成多屏授权通过。
 */
import { expect, test, type Page } from '../../fixtures/test-data'
import { writeEvidence } from '../../helpers/c3-probes'
import { archiveSandboxPage, createSandboxPage, publishRoutes } from '../../helpers/scene-sandbox'

/** 最简预览页：只用于取得受保护预览域来源，验证多屏 API 的授权行为。 */
function buildMultiscreenPage(): string {
  return `<template>
  <main ref="root" class="ms-page"><h1>多屏授权探针</h1></main>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { useStaticPresentation } from '@runtime-kit/public/composables/static/useStaticPresentation.v1'
const root = ref<HTMLElement | null>(null)
useStaticPresentation({ root, mode: 'default' })
</script>
<style scoped>
.ms-page { width: 100%; height: 100%; display: grid; place-items: center; background: #f8fafc; }
h1 { font-size: 36px; color: #0f172a; }
</style>`
}

test('多屏授权：记录 getScreenDetails 的授权结果与屏幕数量', async ({ page, context, visualEditSandbox }, testInfo) => {
  test.setTimeout(3 * 60_000)
  // 无头 Chromium 对 getScreenDetails 一律返回 NotAllowedError，只有有头实例能取到真实屏幕拓扑。
  test.skip(testInfo.project.use.headless === true, '多屏授权必须有头运行（--headed）')
  const api = context.request
  const suffix = `ms-${Date.now()}`
  const createdPages: number[] = []
  let audience: Page | null = null

  try {
    const pageId = await createSandboxPage(api, visualEditSandbox, `${suffix} 多屏页`, buildMultiscreenPage())
    createdPages.push(pageId)
    const previewUrl = await publishRoutes(api, visualEditSandbox.projectId, [{ route: 'ms', pageId }])
    await page.goto(previewUrl)
    const frame = page.frameLocator('iframe#preview').locator('body')
    await expect(frame).toBeVisible()
    const runtimeFrame = page.frames().find(candidate => /preview\.localhost|__preview|:7373/.test(candidate.url()))
    expect(runtimeFrame, '未找到运行时 iframe').toBeTruthy()
    const runtimeUrl = runtimeFrame!.url()
    const origin = new URL(runtimeUrl).origin

    // 先走 Playwright 便捷授权，失败再退回 CDP。注意 CDP 使用 camelCase 的 windowManagement，
    // 与 Web 权限名 window-management 不同；旧版 Chromium 仍可能叫 window-placement。
    const cdp = await context.newCDPSession(page)
    const candidates = [
      { web: 'window-management', cdp: 'windowManagement' },
      { web: 'window-placement', cdp: 'window-placement' },
    ]
    let granted = false
    let grantError: string | null = null
    let grantedPermission: string | null = null
    for (const candidate of candidates) {
      try {
        await context.grantPermissions([candidate.web], { origin })
        granted = true
        grantedPermission = `web:${candidate.web}`
        break
      } catch (error) {
        grantError = (error as Error).message
      }
      try {
        await cdp.send('Browser.grantPermissions', { origin, permissions: [candidate.cdp] as never })
        granted = true
        grantedPermission = `cdp:${candidate.cdp}`
        break
      } catch (error) {
        grantError = `${grantError ? `${grantError} | ` : ''}${(error as Error).message}`
      }
    }

    // getScreenDetails 需要瞬态用户激活，且编辑器预览 iframe 受 Permissions Policy 限制，
    // 因此按真实观众窗口的形态在顶层打开同一运行时地址后再取证。
    const audienceWindow = await context.newPage()
    audience = audienceWindow
    await audienceWindow.goto(runtimeUrl)
    await audienceWindow.locator('.ms-page h1').first().click()

    const probe = await audienceWindow.evaluate(async () => {
      const screenLike = window.screen as Screen & { isExtended?: boolean }
      const base = {
        hasApi: typeof (window as unknown as { getScreenDetails?: unknown }).getScreenDetails === 'function',
        current: { width: screenLike.width, height: screenLike.height, isExtended: screenLike.isExtended ?? null },
      }
      if (!base.hasApi) return { ...base, screens: null as number | null, error: 'NOT_SUPPORTED' }
      try {
        const details = await (window as unknown as { getScreenDetails: () => Promise<{ screens: unknown[] }> }).getScreenDetails()
        return { ...base, screens: details.screens.length, error: null as string | null }
      } catch (error) {
        return { ...base, screens: null as number | null, error: (error as Error).name || 'UNKNOWN' }
      }
    })

    const verdict = !probe.hasApi
      ? 'not-supported'
      : probe.error
        ? 'permission-denied-or-unavailable'
        : (probe.screens ?? 0) > 1
          ? 'multi-display-available'
          : 'single-display-not-verifiable'

    const evidence = {
      kind: 'c3-multiscreen',
      generatedAt: new Date().toISOString(),
      candidateCommit: process.env.C3_CANDIDATE_COMMIT ?? 'working-tree',
      origin,
      // 只记录路径，预览票据（token）不得进入证据。
      topLevelRuntimePath: new URL(runtimeUrl).pathname,
      permissionGranted: granted,
      grantedPermission,
      permissionError: grantError,
      probe,
      verdict,
      note:
        verdict === 'single-display-not-verifiable'
          ? '当前机器只有一块屏幕，跨屏授权无法验证；当前窗口全屏回退不得记为多屏通过。'
          : undefined,
    }
    const evidencePath = await writeEvidence(testInfo, `multiscreen-${suffix}`, evidence)
    testInfo.annotations.push({ type: 'evidence', description: evidencePath })
    console.log(`[c3-multiscreen] verdict=${verdict} screens=${probe.screens ?? 'n/a'} error=${probe.error ?? 'none'}`)

    // 用例只保证探针可执行；是否支持多屏由 C3 依据 verdict 回填支持矩阵。
    expect(probe.current.width).toBeGreaterThan(0)
  } finally {
    await audience?.close().catch(() => undefined)
    for (const pageId of createdPages) await archiveSandboxPage(api, pageId)
  }
})

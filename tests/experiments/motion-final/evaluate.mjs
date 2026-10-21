// 文件功能：封存固定适配模板下的独立 Luna 输出后评分，最多一轮模型反馈，不统计性能。
import { chromium } from '@playwright/test'
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createHash } from 'node:crypto'
import { typecheck, serveVite } from './environment.mjs'
import { checkCandidate } from './checks.mjs'
import { serve } from '../motion-wp01/server.mjs'
const options = Object.fromEntries(process.argv.slice(2).map(arg => arg.replace(/^--/, '').split('=')))
const id = options.case, phase = options.phase ?? 'initial', root = process.cwd(), directory = resolve('tests/experiments/motion-final')
const protocol = JSON.parse(await readFile(resolve(directory, 'protocol.json'), 'utf8'))
const task = id === 'reference' ? { id, detail: 1200, task: 'selfcheck' } : protocol.cases.find(item => item.id === id)
if (!task || !/^(initial|repair|s[0-9]+)$/.test(phase)) throw new Error('候选或阶段名无效')
const output = resolve(root, '.tmp/motion-final', id, phase)
const evidence = id === 'reference' ? output : resolve(directory, 'evidence', id, phase)
const sourcePath = resolve(directory, id === 'reference' ? 'reference.vue' : `candidates/${id}.vue`)
const source = await readFile(sourcePath, 'utf8'), sha = bytes => createHash('sha256').update(bytes).digest('hex')
await mkdir(output, { recursive: true }); await mkdir(evidence, { recursive: true })
await writeFile(resolve(evidence, 'code.vue.txt'), source, { flag: 'wx' })
const result = { id, phase, task, model: id === 'reference' ? 'parent-authored fixture' : protocol.model, sourceSha256: sha(source), inputs: {}, failures: [] }
let environment, assets, browser
try {
  for (const file of ['sdk.ts', 'api-types.ts', 'resource-plan.ts', 'visual.ts', 'harness.ts', 'reference.vue', 'environment.mjs', 'checks.mjs', 'evaluate.mjs', 'task.md', 'protocol.json']) result.inputs[file] = sha(await readFile(resolve(directory, file)))
  result.typecheck = await typecheck(root, id, output)
  if (result.typecheck.status !== 'passed') result.failures.push({ code: 'SFC_TYPECHECK_FAILED', actual: result.typecheck.output })
  else {
    if (/\bas\s+any\b|:\s*any\b|@ts-ignore|@ts-nocheck/.test(source)) result.failures.push({ code: 'AUTHORING_BYPASS', actual: '候选绕过类型检查' })
    environment = await serveVite(root)
    assets = await serve(resolve('.tmp/motion-wp01/assets'), { protectedAssets: true, origin: new URL(environment.url).origin })
    browser = await chromium.launch({ headless: true, args: ['--mute-audio', '--autoplay-policy=no-user-gesture-required'] })
    const page = await browser.newPage({ viewport: { width: 940, height: 650 }, deviceScaleFactor: 1 })
    const errors = []; page.on('pageerror', error => errors.push(error.message))
    await page.goto(`${environment.url}?assets=${encodeURIComponent(assets.url)}`)
    await page.waitForFunction(() => Boolean(window.finalResearch))
    const checked = await checkCandidate(page, id, task.detail, task.callouts)
    result.failures.push(...checked.failures); result.checks = checked.checks; result.samples = checked.samples
    result.browser = browser.version(); result.pageErrors = errors
    if (errors.length) result.failures.push({ code: 'BROWSER_ERROR', actual: errors })
  }
} catch (error) { result.failures.push({ code: 'EVALUATOR_EXCEPTION', actual: error.stack }) }
finally {
  await browser?.close(); await assets?.close(); await environment?.server.close()
  result.status = result.failures.length ? 'failed' : 'passed'
  await writeFile(resolve(evidence, 'result.json'), `${JSON.stringify(result, null, 2)}\n`, { flag: 'wx' })
  console.log(JSON.stringify({ id, phase, status: result.status, feedback: result.failures.slice(0, 6) }))
  if (result.status !== 'passed') process.exitCode = 1
}

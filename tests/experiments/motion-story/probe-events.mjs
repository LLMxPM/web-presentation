// 文件功能：验证两候选原生嵌套时间轴在静默 seek 时的回调行为，不连接资源或采集性能。
import { chromium } from '@playwright/test'
import { prepare } from './environment.mjs'
import assert from 'node:assert/strict'
import { resolve } from 'node:path'
import { mkdir, writeFile } from 'node:fs/promises'

let environment, browser
const result = { scenario: '静默定位父时间轴，检查父子回调', candidates: {} }
try {
  environment = await prepare(process.cwd())
  result.versions = environment.versions
  result.seek = { milliseconds: 900, muteCallbacks: true }
  browser = await chromium.launch({ headless: true })
  const page = await browser.newPage(); await page.goto(environment.url)
  const base = `/@fs/${resolve('.tmp/motion-authoring/deps/node_modules').replaceAll('\\', '/')}`
  result.candidates = await page.evaluate(async base => {
    const { createTimeline } = await import(`${base}/animejs/dist/modules/index.js`)
    const { gsap } = await import(`${base}/gsap/index.js`)
    const animeEvents = [], gsapEvents = [], av = { value: 0 }, gv = { value: 0 }
    const ac = createTimeline({ autoplay: false }).add(av, { value: [0, 1], duration: 1000, ease: 'linear' }).call(() => animeEvents.push('child'), 500).init()
    const ap = createTimeline({ autoplay: false }).sync(ac, 0).call(() => animeEvents.push('parent'), 500).init()
    ap.seek(0, true); animeEvents.length = 0; ap.seek(900, true)
    const anime = { events: [...animeEvents], value: av.value }
    const flatEvents = [], fv = { value: 0 }
    // 工厂复用的是向同一父时间轴追加定义，不再 sync 独立播放器。
    const append = parent => parent.add(fv, { value: [0, 1], duration: 1000, ease: 'linear' }, 0).call(() => flatEvents.push('section'), 500)
    const flat = append(createTimeline({ autoplay: false })).call(() => flatEvents.push('parent'), 500).init()
    flat.seek(0, true); flatEvents.length = 0; flat.seek(900, true)
    const animeAppend = { events: [...flatEvents], value: fv.value }
    const gc = gsap.timeline().to(gv, { value: 1, duration: 1, ease: 'none' }).call(() => gsapEvents.push('child'), [], 0.5)
    const gp = gsap.timeline({ paused: true }).add(gc, 0).call(() => gsapEvents.push('parent'), [], 0.5)
    gp.seek(0, true); gsapEvents.length = 0; gp.seek(0.9, true)
    const gsapResult = { events: [...gsapEvents], value: gv.value }
    ap.revert(); ac.revert(); flat.revert(); gp.kill(); gc.kill(); gsap.ticker.sleep()
    return { anime, animeAppend, gsap: gsapResult }
  }, base)
  assert.deepEqual(result.candidates.anime.events, ['child'])
  assert.deepEqual(result.candidates.animeAppend.events, [])
  assert.deepEqual(result.candidates.gsap.events, [])
  for (const candidate of Object.values(result.candidates)) assert.equal(candidate.value, 0.9)
  result.status = 'observed'
} catch (error) { result.status = 'failed'; result.failure = error.stack; process.exitCode = 1 }
finally {
  await browser?.close(); await environment?.server.close()
  await mkdir('.tmp/motion-story', { recursive: true })
  await writeFile('.tmp/motion-story/events.json', `${JSON.stringify(result, null, 2)}\n`)
  console.log(JSON.stringify(result))
}

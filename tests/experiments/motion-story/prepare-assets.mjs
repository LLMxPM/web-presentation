// 文件功能：单独准备完整故事功能实验的原创素材，避免为重建素材而运行历史性能实验。
import { chromium } from '@playwright/test'
import { access, mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { generateFixtures, fixtureManifest } from '../motion-wp01/fixtures.mjs'
import { encodeVideo } from '../motion-wp01/encode-video.mjs'

const directory = resolve('.tmp/motion-wp01/assets')
const files = ['voice.wav', 'clock.webm', 'animated.glb', 'none.glb', 'missing.glb', 'duplicate.glb']
let browser
try {
  const complete = (await Promise.all(files.map(file => access(resolve(directory, file)).then(() => true, () => false)))).every(Boolean)
  if (!complete || process.argv.includes('--regenerate')) {
    await generateFixtures(directory)
    browser = await chromium.launch({ headless: true })
    const page = await browser.newPage()
    await encodeVideo(page, resolve(directory, 'clock.webm'), chromium.executablePath())
  }
  const manifest = { reused: complete && !process.argv.includes('--regenerate'), fixtures: await fixtureManifest(directory), provenance: 'GLB/视频均由本仓代码生成；Windows 使用 Microsoft Huihui Desktop 离线合成，其他平台使用提示音替身' }
  await mkdir('.tmp/motion-story', { recursive: true })
  await writeFile('.tmp/motion-story/assets.json', `${JSON.stringify(manifest, null, 2)}\n`)
  console.log(JSON.stringify({ status: 'ready', reused: manifest.reused, files: files.length }))
} finally { await browser?.close() }

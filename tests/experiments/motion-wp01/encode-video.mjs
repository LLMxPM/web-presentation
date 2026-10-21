// 文件功能：绘制带时间和帧号的画面，用 Playwright 自带 ffmpeg 编成固定 30fps WebM。
import { execFileSync } from 'node:child_process'
import { readdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'

/** 生成 180 张画面并按时间戳编码，避免 MediaRecorder 实时定时抖动改变样本帧率。 */
export async function encodeVideo(page, path, chromiumPath) {
  const frames = await page.evaluate(() => {
    const canvas = document.createElement('canvas')
    canvas.width = 320; canvas.height = 180
    const ctx = canvas.getContext('2d'), images = []
    for (let frame = 0; frame < 180; frame++) {
      ctx.fillStyle = `hsl(${frame * 2} 65% 30%)`; ctx.fillRect(0, 0, 320, 180)
      ctx.fillStyle = '#fff'; ctx.font = '24px monospace'
      ctx.fillText(`frame ${String(frame).padStart(3, '0')}`, 25, 65)
      ctx.fillText(`${(frame / 30).toFixed(3)}s / 30fps`, 25, 105)
      ctx.fillRect(frame % 300, 140, 15, 15)
      images.push(canvas.toDataURL('image/jpeg', 0.95).split(',')[1])
    }
    return images
  })
  const cache = resolve(dirname(chromiumPath), '../..')
  const entry = (await readdir(cache)).find(name => name.startsWith('ffmpeg-'))
  const ffmpeg = process.env.WP01_FFMPEG || resolve(cache, entry, process.platform === 'win32' ? 'ffmpeg-win64.exe' : process.platform === 'darwin' ? 'ffmpeg-mac' : 'ffmpeg-linux')
  execFileSync(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-f', 'image2pipe', '-c:v', 'mjpeg', '-framerate', '30', '-i', 'pipe:0', '-an', '-c:v', 'libvpx', '-b:v', '600k', '-fflags', '+bitexact', '-flags:v', '+bitexact', '-y', path], { input: Buffer.concat(frames.map(frame => Buffer.from(frame, 'base64'))), windowsHide: true })
}

/**
 * 文件功能：生成 E2E 使用的短促真实 WAV，支持 data URI 与资源上传。
 */

/** 生成指定时长的 440Hz 单声道 PCM WAV。 */
export function toneWavBuffer(seconds: number): Buffer {
  const sampleRate = 8_000
  const samples = Math.round(sampleRate * seconds)
  const bytes = Buffer.alloc(44 + samples * 2)
  bytes.write('RIFF', 0)
  bytes.writeUInt32LE(bytes.length - 8, 4)
  bytes.write('WAVEfmt ', 8)
  bytes.writeUInt32LE(16, 16)
  bytes.writeUInt16LE(1, 20)
  bytes.writeUInt16LE(1, 22)
  bytes.writeUInt32LE(sampleRate, 24)
  bytes.writeUInt32LE(sampleRate * 2, 28)
  bytes.writeUInt16LE(2, 32)
  bytes.writeUInt16LE(16, 34)
  bytes.write('data', 36)
  bytes.writeUInt32LE(samples * 2, 40)
  for (let index = 0; index < samples; index += 1) {
    bytes.writeInt16LE(Math.round(Math.sin(2 * Math.PI * 440 * index / sampleRate) * 8192), 44 + index * 2)
  }
  return bytes
}

/** 生成 0.7 秒 440Hz 单声道 PCM WAV。 */
export function shortWavBuffer(): Buffer {
  return toneWavBuffer(0.7)
}

/** 生成可直接嵌入页面的短 WAV URL。 */
export function shortWavDataUri(): string {
  return `data:audio/wav;base64,${shortWavBuffer().toString('base64')}`
}

/** 生成覆盖长导出窗口的一次性 WAV URL。 */
export function longWavDataUri(seconds = 30): string {
  return `data:audio/wav;base64,${toneWavBuffer(seconds).toString('base64')}`
}

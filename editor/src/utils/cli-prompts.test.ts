/**
 * 文件功能：验证面向桌面智能体与 CLI 的提示词和命令生成逻辑。
 */
import { describe, expect, it } from 'vitest'

import {
  buildAgentInstallPrompt,
  buildAgentReLoginPrompt,
  buildManualLoginCommand,
  buildManualSkillInstallCommand,
  resolveCurrentEndpoint,
} from './cli-prompts'

describe('cli-prompts utils', () => {
  it('buildAgentInstallPrompt 应包含 wp skill install 并由 CLI 自行引导安装位置', () => {
    const prompt = buildAgentInstallPrompt({
      endpoint: 'https://presentation.example.com',
      token: 'wp_pat_mock_123',
    })

    expect(prompt).toContain('https://presentation.example.com')
    expect(prompt).toContain('wp_pat_mock_123')
    expect(prompt).toContain('wp skill install')
    expect(prompt).not.toContain('--scope project')
    expect(prompt).toContain('uv tool install web-presentation-cli')
    expect(prompt).toContain('wp doctor')
  })

  it('buildAgentReLoginPrompt 应生成精简的重新登录提示词且不包含重复安装步骤', () => {
    const prompt = buildAgentReLoginPrompt({
      endpoint: 'http://192.168.1.100:8080',
      token: 'wp_pat_new_789',
    })

    expect(prompt).toContain('http://192.168.1.100:8080')
    expect(prompt).toContain('wp_pat_new_789')
    expect(prompt).toContain('wp whoami')
    expect(prompt).toContain('wp doctor')
    expect(prompt).not.toContain('uv tool install')
    expect(prompt).not.toContain('wp skill install')
  })

  it('buildManualLoginCommand 应正确拼接命令行', () => {
    expect(buildManualLoginCommand('http://127.0.0.1:8000', 'test_token')).toBe(
      'wp login --endpoint http://127.0.0.1:8000 --token test_token'
    )
    expect(buildManualLoginCommand('http://127.0.0.1:8000')).toBe(
      'wp login --endpoint http://127.0.0.1:8000'
    )
  })

  it('buildManualSkillInstallCommand 应支持默认无参或拼接作用域', () => {
    expect(buildManualSkillInstallCommand()).toBe('wp skill install')
    expect(buildManualSkillInstallCommand('project')).toBe('wp skill install --scope project')
    expect(buildManualSkillInstallCommand('global')).toBe('wp skill install --scope global')
  })

  it('resolveCurrentEndpoint 应返回当前 window.location.origin', () => {
    expect(resolveCurrentEndpoint()).toBeTruthy()
  })
})

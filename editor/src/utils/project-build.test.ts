/**
 * 文件功能：验证项目整包构建工具方法，包括 baseUrl、状态展示与体积格式化。
 */

import { describe, expect, it } from 'vitest'

import { formatProjectBuildArtifactSize, getProjectBuildStatusMeta, normalizeProjectBuildBaseUrl } from './project-build'

describe('project build baseUrl', () => {
  it('应规范化支持的部署基路径', () => {
    expect(normalizeProjectBuildBaseUrl(undefined)).toBe('./')
    expect(normalizeProjectBuildBaseUrl('./')).toBe('./')
    expect(normalizeProjectBuildBaseUrl('/demo')).toBe('/demo/')
    expect(normalizeProjectBuildBaseUrl('/nested/path/')).toBe('/nested/path/')
  })

  it('应拒绝非法部署基路径', () => {
    expect(() => normalizeProjectBuildBaseUrl('https://example.com/demo')).toThrow('URL')
    expect(() => normalizeProjectBuildBaseUrl('//cdn.example.com/demo')).toThrow('URL')
    expect(() => normalizeProjectBuildBaseUrl('demo')).toThrow('仅支持')
  })

  it('应返回正确的构建状态展示文案', () => {
    expect(getProjectBuildStatusMeta('succeeded').label).toBe('构建成功')
    expect(getProjectBuildStatusMeta('failed').label).toBe('构建失败')
    expect(getProjectBuildStatusMeta('running').label).toBe('构建中')
    expect(getProjectBuildStatusMeta('pending').label).toBe('排队中')
  })

  it('应格式化构建产物体积', () => {
    expect(formatProjectBuildArtifactSize(null)).toBe('未生成')
    expect(formatProjectBuildArtifactSize(512)).toBe('512 B')
    expect(formatProjectBuildArtifactSize(2048)).toBe('2.0 KB')
    expect(formatProjectBuildArtifactSize(3 * 1024 * 1024)).toBe('3.0 MB')
  })
})

/**
 * 文件功能：提供 Runtime 文件访问的公共授权、路径校验与文件读写能力。
 */

import { createHash } from 'crypto'
import {
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  realpathSync,
  rmSync,
  statSync,
  unlinkSync,
  writeFileSync,
} from 'fs'
import { basename, extname, isAbsolute, relative, resolve } from 'path'

export type FileOperation = 'read' | 'write' | 'delete' | 'upload'

export interface AllowedDirRule {
  path: string
  read: boolean
  write: boolean
  delete: boolean
  upload: boolean
}

export interface FileInfo {
  name: string
  path: string
  isDirectory: boolean
  size: number
  modified: string
}

export interface FileWriteResult {
  path: string
  fileName: string
  contentHash: string
}

const BLOCKED_SEGMENTS = new Set(['.git', 'node_modules', 'dist'])

/**
 * 文件访问异常，统一携带状态码与错误码，便于中间件层映射响应。
 */
export class FileAccessError extends Error {
  statusCode: number
  code: string

  constructor(statusCode: number, code: string, message: string) {
    super(message)
    this.statusCode = statusCode
    this.code = code
  }
}

/**
 * 规范化相对路径，并拒绝绝对路径、父级穿越与敏感段。
 * @param rawPath 原始相对路径
 * @param allowEmpty 是否允许空路径
 * @returns 规范化后的相对路径
 */
export function normalizeRelativePath(rawPath: string, allowEmpty: boolean = false): string {
  const trimmed = String(rawPath || '').trim()
  if (!trimmed) {
    if (allowEmpty) {
      return ''
    }
    throw new FileAccessError(400, 'PATH_REQUIRED', '路径不能为空。')
  }

  if (trimmed.includes('\0')) {
    throw new FileAccessError(400, 'PATH_INVALID', '路径包含非法字符。')
  }

  const normalized = trimmed.replace(/\\/g, '/')
  if (normalized.startsWith('/')) {
    throw new FileAccessError(400, 'PATH_INVALID', '路径必须是相对路径。')
  }
  if (isAbsolute(normalized)) {
    throw new FileAccessError(400, 'PATH_INVALID', '路径必须是相对路径。')
  }

  const segments = normalized.split('/').filter(Boolean)
  if (segments.length === 0) {
    if (allowEmpty) {
      return ''
    }
    throw new FileAccessError(400, 'PATH_REQUIRED', '路径不能为空。')
  }

  for (const segment of segments) {
    if (segment === '.' || segment === '..') {
      throw new FileAccessError(400, 'PATH_INVALID', '路径不能包含当前目录或父目录跳转。')
    }
    if (BLOCKED_SEGMENTS.has(segment) || segment.startsWith('.env')) {
      throw new FileAccessError(403, 'PATH_BLOCKED', '目标路径包含受保护目录或文件。')
    }
  }

  return segments.join('/')
}

/**
 * 计算内容的 SHA256 哈希值。
 * @param content 文件内容
 * @returns 十六进制哈希串
 */
export function hashContent(content: Buffer | string): string {
  return createHash('sha256').update(content).digest('hex')
}

/**
 * 判断子路径是否命中白名单目录本身或其子路径。
 * @param candidatePath 待校验路径
 * @param allowedPath 白名单目录
 * @returns 是否命中
 */
function isWithinAllowedPath(candidatePath: string, allowedPath: string): boolean {
  return candidatePath === allowedPath || candidatePath.startsWith(`${allowedPath}/`)
}

/**
 * 向上查找最近存在的祖先目录，便于校验符号链接逃逸。
 * @param absolutePath 绝对路径
 * @returns 最近存在的祖先目录
 */
function findExistingAncestor(absolutePath: string): string {
  let currentPath = absolutePath
  while (!existsSync(currentPath)) {
    const parentPath = resolve(currentPath, '..')
    if (parentPath === currentPath) {
      break
    }
    currentPath = parentPath
  }
  return currentPath
}

/**
 * 校验真实路径是否仍然位于 Runtime 根目录内。
 * @param rootRealPath 根目录真实路径
 * @param absolutePath 目标绝对路径
 */
function ensurePathInsideRoot(rootRealPath: string, absolutePath: string): void {
  const existingPath = findExistingAncestor(absolutePath)
  const realExistingPath = realpathSync(existingPath)
  const relativePath = relative(rootRealPath, realExistingPath)
  if (relativePath.startsWith('..') || isAbsolute(relativePath)) {
    throw new FileAccessError(403, 'PATH_ESCAPE', '目标路径越过了 Runtime 根目录。')
  }

  if (existsSync(absolutePath)) {
    const realTargetPath = realpathSync(absolutePath)
    const relativeTargetPath = relative(rootRealPath, realTargetPath)
    if (relativeTargetPath.startsWith('..') || isAbsolute(relativeTargetPath)) {
      throw new FileAccessError(403, 'PATH_ESCAPE', '目标路径越过了 Runtime 根目录。')
    }
  }
}

/**
 * 构建文件访问控制器。
 * @param rootDir Runtime 根目录
 * @param allowedDirs 白名单目录配置
 * @returns 文件访问能力集合
 */
export function createFileAccessController(rootDir: string, allowedDirs: AllowedDirRule[]) {
  const rootRealPath = realpathSync(rootDir)
  const normalizedAllowedDirs = allowedDirs.map((rule) => ({
    ...rule,
    path: normalizeRelativePath(rule.path),
  }))

  /**
   * 解析并校验目标路径。
   * @param rawPath 原始相对路径
   * @param operation 操作类型
   * @param allowEmpty 是否允许空路径
   * @returns 规范化路径与绝对路径
   */
  function authorize(rawPath: string, operation: FileOperation, allowEmpty: boolean = false) {
    const normalizedPath = normalizeRelativePath(rawPath, allowEmpty)
    const matchedRule = normalizedAllowedDirs.find((rule) => (
      isWithinAllowedPath(normalizedPath, rule.path) && rule[operation]
    ))

    if (!matchedRule) {
      throw new FileAccessError(403, 'ACCESS_DENIED', '目标路径不在允许的操作范围内。')
    }

    const absolutePath = resolve(rootDir, normalizedPath)
    const relativePath = relative(rootDir, absolutePath)
    if (relativePath.startsWith('..') || isAbsolute(relativePath)) {
      throw new FileAccessError(403, 'PATH_ESCAPE', '目标路径越过了 Runtime 根目录。')
    }

    ensurePathInsideRoot(rootRealPath, absolutePath)
    return { normalizedPath, absolutePath, rule: matchedRule }
  }

  /**
   * 列出目录下的文件与子目录。
   * @param dirPath 目标目录
   * @returns 文件信息列表
   */
  function listDirectory(dirPath: string): FileInfo[] {
    const { absolutePath } = authorize(dirPath, 'read')
    if (!existsSync(absolutePath)) {
      throw new FileAccessError(404, 'DIRECTORY_NOT_FOUND', '目录不存在。')
    }

    const stats = statSync(absolutePath)
    if (!stats.isDirectory()) {
      throw new FileAccessError(400, 'NOT_A_DIRECTORY', '目标不是目录。')
    }

    return readdirSync(absolutePath)
      .map((name) => {
        const entryPath = resolve(absolutePath, name)
        const entryStats = statSync(entryPath)
        return {
          name,
          path: relative(rootDir, entryPath).replace(/\\/g, '/'),
          isDirectory: entryStats.isDirectory(),
          size: entryStats.size,
          modified: entryStats.mtime.toISOString(),
        }
      })
      .sort((left, right) => {
        if (left.isDirectory !== right.isDirectory) {
          return left.isDirectory ? -1 : 1
        }
        return left.name.localeCompare(right.name)
      })
  }

  /**
   * 读取 UTF-8 文本文件。
   * @param filePath 目标文件路径
   * @returns 文本内容
   */
  function readTextFile(filePath: string): string {
    const { absolutePath } = authorize(filePath, 'read')
    if (!existsSync(absolutePath)) {
      throw new FileAccessError(404, 'FILE_NOT_FOUND', '文件不存在。')
    }

    const stats = statSync(absolutePath)
    if (!stats.isFile()) {
      throw new FileAccessError(400, 'NOT_A_FILE', '目标不是文件。')
    }
    return readFileSync(absolutePath, 'utf-8')
  }

  /**
   * 写入 UTF-8 文本文件，并在需要时校验旧内容哈希。
   * @param filePath 目标文件路径
   * @param content 文本内容
   * @param expectedHash 期望的旧内容哈希
   * @returns 写入结果
   */
  function writeTextFile(filePath: string, content: string, expectedHash?: string): FileWriteResult {
    const { absolutePath, normalizedPath } = authorize(filePath, 'write')
    if (expectedHash && existsSync(absolutePath)) {
      const currentHash = hashContent(readFileSync(absolutePath))
      if (currentHash !== expectedHash) {
        throw new FileAccessError(409, 'FILE_HASH_MISMATCH', '文件内容已变化，请刷新后重试。')
      }
    }

    mkdirSync(resolve(absolutePath, '..'), { recursive: true })
    writeFileSync(absolutePath, content, 'utf-8')
    return {
      path: normalizedPath,
      fileName: basename(normalizedPath),
      contentHash: hashContent(Buffer.from(content, 'utf-8')),
    }
  }

  /**
   * 写入二进制文件。
   * @param filePath 目标文件路径
   * @param content 二进制内容
   * @param overwrite 是否允许覆盖
   * @returns 写入结果
   */
  function writeBinaryFile(filePath: string, content: Buffer, overwrite: boolean = true): FileWriteResult {
    const { absolutePath, normalizedPath } = authorize(filePath, 'upload')
    if (!overwrite && existsSync(absolutePath)) {
      throw new FileAccessError(409, 'FILE_EXISTS', '目标文件已存在。')
    }

    mkdirSync(resolve(absolutePath, '..'), { recursive: true })
    writeFileSync(absolutePath, content)
    return {
      path: normalizedPath,
      fileName: basename(normalizedPath),
      contentHash: hashContent(content),
    }
  }

  /**
   * 删除文件。
   * @param filePath 目标文件路径
   * @returns 删除结果
   */
  function deleteFile(filePath: string): FileWriteResult {
    const { absolutePath, normalizedPath } = authorize(filePath, 'delete')
    if (!existsSync(absolutePath)) {
      throw new FileAccessError(404, 'FILE_NOT_FOUND', '文件不存在。')
    }

    const stats = statSync(absolutePath)
    if (!stats.isFile()) {
      throw new FileAccessError(400, 'NOT_A_FILE', '目标不是文件。')
    }

    const contentHash = hashContent(readFileSync(absolutePath))
    unlinkSync(absolutePath)
    return {
      path: normalizedPath,
      fileName: basename(normalizedPath),
      contentHash,
    }
  }

  /**
   * 创建目录。
   * @param dirPath 目标目录路径
   * @returns 创建结果
   */
  function makeDirectory(dirPath: string): FileWriteResult {
    const { absolutePath, normalizedPath } = authorize(dirPath, 'write')
    mkdirSync(absolutePath, { recursive: true })
    return {
      path: normalizedPath,
      fileName: basename(normalizedPath),
      contentHash: hashContent(Buffer.from(normalizedPath, 'utf-8')),
    }
  }

  /**
   * 删除目录。
   * @param dirPath 目标目录路径
   * @param recursive 是否递归删除
   * @returns 删除结果
   */
  function removeDirectory(dirPath: string, recursive: boolean = true): FileWriteResult {
    const { absolutePath, normalizedPath } = authorize(dirPath, 'delete')
    if (!existsSync(absolutePath)) {
      throw new FileAccessError(404, 'DIRECTORY_NOT_FOUND', '目录不存在。')
    }

    const stats = statSync(absolutePath)
    if (!stats.isDirectory()) {
      throw new FileAccessError(400, 'NOT_A_DIRECTORY', '目标不是目录。')
    }

    rmSync(absolutePath, { recursive, force: false })
    return {
      path: normalizedPath,
      fileName: basename(normalizedPath),
      contentHash: hashContent(Buffer.from(normalizedPath, 'utf-8')),
    }
  }

  return {
    authorize,
    listDirectory,
    readTextFile,
    writeTextFile,
    writeBinaryFile,
    deleteFile,
    makeDirectory,
    removeDirectory,
  }
}

/**
 * 将目录路径与文件名拼接为统一的相对路径。
 * @param dirPath 目标目录
 * @param fileName 文件名
 * @returns 拼接后的相对路径
 */
export function joinRelativePath(dirPath: string, fileName: string): string {
  const normalizedDir = normalizeRelativePath(dirPath)
  const normalizedFileName = normalizeRelativePath(fileName)
  if (normalizedFileName.includes('/')) {
    throw new FileAccessError(400, 'FILE_NAME_INVALID', '文件名不能包含目录分隔符。')
  }
  return `${normalizedDir}/${normalizedFileName}`
}

/**
 * 根据扩展名简单判断是否为文本文件。
 * @param filePath 文件路径
 * @returns 是否可按 UTF-8 读取
 */
export function isLikelyTextFile(filePath: string): boolean {
  const extension = extname(filePath).toLowerCase()
  return ['', '.vue', '.ts', '.js', '.json', '.md', '.txt', '.yaml', '.yml', '.css', '.svg'].includes(extension)
}

/**
 * 文件功能：集中维护平台 E2E 环境常量（Backend 地址、storageState 路径与 seed 版本），供 globalSetup 与夹具复用。
 */

/** Backend 基础地址；与 scripts/testing/service-env.mjs 的回退顺序保持一致。 */
export const E2E_BACKEND_URL = process.env.E2E_API_BASE_URL || process.env.BACKEND_BASE_URL || 'http://127.0.0.1:8000'

/** storageState 落盘路径：敏感临时文件，已被 .gitignore 的 test-results/ 规则覆盖，不得上传为 CI artifact。 */
export const STORAGE_STATE_PATH = 'test-results/e2e/storage-state.json'

/**
 * 期望的 smoke 数据协议版本，必须与 backend/app/scripts/test_data.py 的 SEED_VERSION 一致；
 * 两侧一致性由 tests/contracts/e2e-backend 契约测试保护。
 */
export const EXPECTED_SEED_VERSION = 2

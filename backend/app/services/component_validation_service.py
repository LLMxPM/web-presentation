"""文件功能：编排组件候选的 Runtime 编译、真实渲染、结果归一化与临时 artifact 清理。"""

from __future__ import annotations

import hashlib
import json
import logging

from app.core.text_normalizer import normalize_text_to_lf
from app.models.enums import WorkspaceComponentType
from app.schemas.component_validation import ComponentValidationResult
from app.services.capture_viewport_resolver import CaptureViewport
from app.services.component_render_diagnostics_service import ComponentRenderDiagnosticsService
from app.services.component_validation_profile import COMPONENT_VALIDATION_PROFILE_VERSION
from app.services.runtime_artifact_store import RuntimeArtifactStore
from app.services.runtime_diagnostics_client import RuntimeDiagnosticsClient
from app.services.token_service import TokenService

logger = logging.getLogger(__name__)


class ComponentValidationService:
    """组件校验编排服务，统一独立 check 与三类 AI 写工具的结果语义。"""

    def __init__(
        self,
        runtime_client: RuntimeDiagnosticsClient,
        render_diagnostics_service: ComponentRenderDiagnosticsService,
    ) -> None:
        self.runtime_client = runtime_client
        self.render_diagnostics_service = render_diagnostics_service

    async def dispatch(
        self,
        *,
        artifact_id: str,
        workspace_id: int,
        project_id: int | None,
        label: str,
        patch_repaired: bool,
        canonical_diff: str | None,
        preview_url: str,
        viewport: CaptureViewport,
        profile_key: str,
        candidate_hash: str,
    ) -> dict[str, object]:
        """执行组件编译与真实渲染诊断，并保证临时 artifact 被清理。"""

        try:
            diagnostics_token = TokenService.generate_runtime_diagnostics_command_token(
                artifact_id=artifact_id,
                workspace_id=workspace_id,
                project_id=project_id,
            )
            compile_result = await self.runtime_client.dispatch_artifact_diagnostics(
                artifact_id=artifact_id,
                diagnostics_token=diagnostics_token,
                label=label,
            )
            compile_diagnostics = self.normalize_stage_diagnostics(
                compile_result.get("diagnostics"),
                stage="compile",
            )
            base_result: dict[str, object] = {
                **compile_result,
                "candidate_hash": candidate_hash,
                "validation_profile_version": COMPONENT_VALIDATION_PROFILE_VERSION,
                "profile_key": profile_key,
                "patch_repaired": patch_repaired,
                "canonical_diff": canonical_diff,
                "retryable": False,
                "diagnostics": compile_diagnostics,
                "scenarios": [],
            }
            if not self._compile_passed(compile_result):
                return self.validated_result({
                    **base_result,
                    "success": False,
                    "valid": False,
                    "status": "failed",
                    "stages": {"contract": "passed", "compile": "failed", "render": "skipped"},
                })

            render_result = await self.render_diagnostics_service.diagnose_preview(
                preview_url,
                viewport,
                profile_key=profile_key,
            )
            render_status = str(render_result.get("status") or "unavailable")
            render_diagnostics = self.normalize_stage_diagnostics(
                render_result.get("diagnostics"),
                stage="render",
            )
            diagnostics = [*compile_diagnostics, *render_diagnostics]
            if render_status == "unavailable":
                return self.validated_result({
                    **base_result,
                    "success": False,
                    "valid": False,
                    "status": "unavailable",
                    "retryable": True,
                    "summary": "组件编译通过，但真实渲染诊断暂不可用。",
                    "stages": {"contract": "passed", "compile": "passed", "render": "unavailable"},
                    "diagnostics": diagnostics,
                    "scenarios": render_result.get("scenarios") or [],
                })

            has_errors = any(item.get("severity") == "error" for item in diagnostics)
            has_warnings = any(item.get("severity") == "warning" for item in diagnostics)
            status = "failed" if has_errors else ("passed_with_warnings" if has_warnings else "passed")
            return self.validated_result({
                **base_result,
                "success": not has_errors,
                "valid": not has_errors,
                "status": status,
                "summary": self._build_summary(status, render_result.get("scenarios")),
                "stages": {
                    "contract": "passed",
                    "compile": "passed",
                    "render": "failed" if has_errors else (
                        "passed_with_warnings" if has_warnings else "passed"
                    ),
                },
                "diagnostics": diagnostics,
                "scenarios": render_result.get("scenarios") or [],
            })
        except Exception:  # noqa: BLE001
            logger.warning(
                "组件 Runtime 编译诊断不可用。",
                extra={"event": "runtime.component_diagnostics.unavailable", "artifact_id": artifact_id},
                exc_info=True,
            )
            return self.validated_result({
                "success": False,
                "valid": False,
                "status": "unavailable",
                "retryable": True,
                "artifact_id": artifact_id,
                "candidate_hash": candidate_hash,
                "validation_profile_version": COMPONENT_VALIDATION_PROFILE_VERSION,
                "profile_key": profile_key,
                "patch_repaired": patch_repaired,
                "canonical_diff": canonical_diff,
                "summary": "组件 Runtime 编译诊断暂不可用，请稍后重试。",
                "stages": {"contract": "passed", "compile": "unavailable", "render": "skipped"},
                "diagnostics": [{
                    "severity": "error",
                    "stage": "compile",
                    "source": "infrastructure",
                    "code": "COMPONENT_CHECK_UNAVAILABLE",
                    "message": "组件 Runtime 编译诊断暂不可用，请稍后重试。",
                }],
                "scenarios": [],
            })
        finally:
            try:
                await RuntimeArtifactStore().delete_artifact(artifact_id)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "组件 Runtime 诊断 artifact 主动清理失败，将由 TTL 清扫兜底。",
                    extra={"event": "runtime.component_artifact.cleanup.failed", "artifact_id": artifact_id},
                    exc_info=True,
                )

    @staticmethod
    def contract_failed_result(
        *,
        code: str,
        message: str,
        canonical_diff: str | None = None,
    ) -> dict[str, object]:
        """构造组件契约阶段失败结果。"""

        return ComponentValidationService.validated_result({
            "success": False,
            "valid": False,
            "status": "failed",
            "retryable": False,
            "artifact_id": None,
            "summary": message,
            "message": message,
            "patch_repaired": False,
            "canonical_diff": canonical_diff,
            "validation_profile_version": COMPONENT_VALIDATION_PROFILE_VERSION,
            "stages": {"contract": "failed", "compile": "skipped", "render": "skipped"},
            "diagnostics": [{
                "severity": "error",
                "stage": "contract",
                "source": "backend-contract",
                "code": code,
                "message": message,
            }],
            "scenarios": [],
        })

    @staticmethod
    def enrich_contract_failure(result: dict[str, object]) -> dict[str, object]:
        """为候选输入或 edits 失败补齐组件统一阶段字段。"""

        return ComponentValidationService.validated_result({
            **result,
            "valid": False,
            "retryable": False,
            "validation_profile_version": COMPONENT_VALIDATION_PROFILE_VERSION,
            "stages": {"contract": "failed", "compile": "skipped", "render": "skipped"},
            "diagnostics": ComponentValidationService.normalize_stage_diagnostics(
                result.get("diagnostics"),
                stage="contract",
            ),
            "scenarios": [],
        })

    @staticmethod
    def build_candidate_hash(
        *,
        content: str,
        preview_schema: str | None,
        component_type: WorkspaceComponentType,
    ) -> str:
        """对组件固有候选生成稳定 hash；执行期页面尺寸与基础字号不进入候选身份。"""

        payload = json.dumps(
            {
                "content": normalize_text_to_lf(content),
                "preview_schema": preview_schema,
                "component_type": component_type.value,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"

    @staticmethod
    def normalize_stage_diagnostics(value: object, *, stage: str) -> list[dict[str, object]]:
        """为 Runtime 旧诊断补齐 stage，保留已经存在的组件诊断结构。"""

        if not isinstance(value, list):
            return []
        return [
            {**item, "stage": item.get("stage") or stage}
            for item in value
            if isinstance(item, dict)
        ]

    @staticmethod
    def validated_result(result: dict[str, object]) -> dict[str, object]:
        """使用正式 Pydantic Schema 校验结果，同时保留 Runtime 扩展字段。"""

        return ComponentValidationResult.model_validate(result).model_dump(mode="python")

    @staticmethod
    def _compile_passed(result: dict[str, object]) -> bool:
        """判断 Runtime 编译诊断是否通过。"""

        return bool(result.get("success") is True or result.get("status") == "passed")

    @staticmethod
    def _build_summary(status: str, scenarios: object) -> str:
        """按整体状态和已执行场景数生成模型反馈。"""

        scenario_count = len(scenarios) if isinstance(scenarios, list) else 0
        if status == "failed":
            return f"组件编译通过，但真实渲染检查失败；已执行 {scenario_count} 个场景。"
        if status == "passed_with_warnings":
            return f"组件可以编译并真实渲染；已执行 {scenario_count} 个场景，存在布局或资源警告。"
        return f"组件可以编译并真实渲染；{scenario_count} 个场景全部通过。"

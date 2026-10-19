"""文件功能：读写项目音频音量与 cue 绑定，并校验资源归属与可用性。

音量保存在项目 JSON 列，cue 绑定使用独立表；读取时合并为完整设置，写入时先
校验全部资源再在一个事务内替换，避免非法绑定造成部分落库。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.asset import WorkspaceAsset
from app.models.enums import AssetType, RecordStatus
from app.models.project_audio_cue import ProjectAudioCueBinding
from app.models.workspace import Project
from app.schemas.audio import (
    AUDIO_CAPABILITY_AUDIO_CUES,
    AudioCueBindingInput,
    ProjectAudioSettings,
    ResolvedAudioCueBinding,
    build_runtime_audio_config,
    default_project_audio_settings,
    load_audio_volume_settings,
)
from app.services.audio_capability_gate import is_audio_capability_open


class ProjectAudioSettingsService:
    """项目音频设置服务；所有写入都按项目当前工作空间校验绑定资源。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def load_settings(self, project: Project) -> ProjectAudioSettings:
        """读取单个项目的完整音频设置，历史空值补默认音量。"""

        loaded = await self.load_settings_many([project.id])
        return loaded.get(project.id) or default_project_audio_settings()

    async def load_settings_many(self, project_ids: Sequence[int]) -> dict[int, ProjectAudioSettings]:
        """批量读取项目音频设置，避免项目列表产生逐项查询。"""

        if not project_ids:
            return {}
        rows = list(
            await self.session.scalars(
                select(ProjectAudioCueBinding)
                .where(ProjectAudioCueBinding.project_id.in_(project_ids))
                .order_by(ProjectAudioCueBinding.project_id, ProjectAudioCueBinding.cue_key)
            )
        )
        grouped: dict[int, list[ProjectAudioCueBinding]] = defaultdict(list)
        for row in rows:
            grouped[row.project_id].append(row)

        projects = list(
            await self.session.scalars(
                select(Project).where(Project.id.in_(project_ids))
            )
        )
        result: dict[int, ProjectAudioSettings] = {}
        for project in projects:
            volume = load_audio_volume_settings(project.audio_settings_json)
            result[project.id] = ProjectAudioSettings(
                **volume.model_dump(mode="python"),
                cue_bindings=[
                    AudioCueBindingInput(
                        key=row.cue_key,
                        asset_id=row.asset_id,
                        gain_percent=row.gain_percent,
                    )
                    for row in grouped.get(project.id, [])
                ],
            )
        return result

    async def validate_bindings(
        self,
        workspace_id: int,
        bindings: Iterable[AudioCueBindingInput],
    ) -> None:
        """校验全部绑定资源属于当前工作空间、active 且类型为 audio。

        只读取不写入；任何一项不合法都抛出 422，错误文案按 cue key 有界列出。
        """

        binding_list = list(bindings)
        if not binding_list:
            return
        asset_ids = {binding.asset_id for binding in binding_list}
        assets = {
            asset.id: asset
            for asset in await self.session.scalars(
                select(WorkspaceAsset)
                .where(WorkspaceAsset.workspace_id == workspace_id)
                .where(WorkspaceAsset.id.in_(asset_ids))
            )
        }
        issues: list[str] = []
        for binding in binding_list:
            asset = assets.get(binding.asset_id)
            if asset is None:
                issues.append(f"{binding.key} 引用的资源不存在或不属于当前工作空间。")
            elif asset.status != RecordStatus.ACTIVE.value:
                issues.append(f"{binding.key} 引用的资源已归档或不可用。")
            elif asset.asset_type != AssetType.AUDIO.value:
                issues.append(f"{binding.key} 只能绑定 audio 类型资源。")
        if issues:
            raise AppException(
                status_code=422,
                code="PROJECT_AUDIO_CUE_ASSET_INVALID",
                detail="；".join(issues[:10]),
            )

    async def replace_settings(
        self,
        project: Project,
        settings: ProjectAudioSettings,
        *,
        operator_id: int | None = None,
        commit: bool = True,
    ) -> None:
        """整体替换音量与 cue 绑定；校验失败时不修改任何持久化状态。"""

        await self.validate_bindings(project.workspace_id, settings.cue_bindings)
        project.audio_settings_json = settings.volume_settings().model_dump(mode="python")
        if operator_id is not None:
            project.updated_by = operator_id
            project.updated_at = utc_now()
        await self._replace_cues(project.id, settings.cue_bindings)
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()

    async def replace_cues(
        self,
        project_id: int,
        bindings: Iterable[AudioCueBindingInput],
    ) -> None:
        """只替换 cue 绑定；调用方负责提交和资源校验。"""

        await self._replace_cues(project_id, bindings)

    async def clear_cue_bindings(
        self,
        project: Project,
        *,
        operator_id: int | None = None,
        commit: bool = False,
    ) -> None:
        """只删除项目 cue 绑定，保留三段音量与其它配置。

        清空是单条 DELETE，不读出再写回音量，避免覆盖两次请求之间其它客户端提交的音量更新；
        事务边界与 `replace_settings` 一致，由调用方决定提交或 flush。
        """

        await self.session.execute(
            delete(ProjectAudioCueBinding).where(
                ProjectAudioCueBinding.project_id == project.id
            )
        )
        if operator_id is not None:
            project.updated_by = operator_id
            project.updated_at = utc_now()
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()

    async def list_cue_bindings(
        self,
        project_id: int,
    ) -> list[ProjectAudioCueBinding]:
        """按 cue key 稳定顺序返回项目绑定，供引用摘要与快照使用。"""

        return list(
            await self.session.scalars(
                select(ProjectAudioCueBinding)
                .where(ProjectAudioCueBinding.project_id == project_id)
                .order_by(ProjectAudioCueBinding.cue_key)
            )
        )

    async def collect_cue_asset_names(self, project_id: int) -> list[str]:
        """收集 cue 绑定的全部资源名，供模板导出识别缺失与自动打包。"""

        rows = await self.session.execute(
            select(WorkspaceAsset.name)
            .join(ProjectAudioCueBinding, ProjectAudioCueBinding.asset_id == WorkspaceAsset.id)
            .where(ProjectAudioCueBinding.project_id == project_id)
            .order_by(ProjectAudioCueBinding.cue_key)
        )
        return [str(name).strip() for name in rows.scalars().all() if str(name).strip()]

    async def build_export_payload(self, project: Project) -> dict[str, object]:
        """构建模板包使用的音量与逻辑名 cue，不携带数据库 ID 或票据。"""

        volume = load_audio_volume_settings(project.audio_settings_json)
        rows = await self.session.execute(
            select(
                ProjectAudioCueBinding.cue_key,
                ProjectAudioCueBinding.gain_percent,
                WorkspaceAsset.name,
            )
            .join(WorkspaceAsset, WorkspaceAsset.id == ProjectAudioCueBinding.asset_id)
            .where(ProjectAudioCueBinding.project_id == project.id)
            .order_by(ProjectAudioCueBinding.cue_key)
        )
        return {
            **volume.model_dump(mode="python"),
            "cue_bindings": [
                {
                    "key": cue_key,
                    "asset_name": asset_name,
                    "gain_percent": gain_percent,
                }
                for cue_key, gain_percent, asset_name in rows.all()
            ],
        }

    async def build_external_payload(
        self,
        project_id: int,
        settings: ProjectAudioSettings,
    ) -> dict[str, object]:
        """构建 External API 读取摘要：保留资产 ID，并附带逻辑名、类型和状态。"""

        rows = await self.session.execute(
            select(
                ProjectAudioCueBinding.cue_key,
                ProjectAudioCueBinding.gain_percent,
                WorkspaceAsset.id,
                WorkspaceAsset.name,
                WorkspaceAsset.asset_type,
                WorkspaceAsset.status,
            )
            .join(WorkspaceAsset, WorkspaceAsset.id == ProjectAudioCueBinding.asset_id)
            .where(ProjectAudioCueBinding.project_id == project_id)
            .order_by(ProjectAudioCueBinding.cue_key)
        )
        return {
            **settings.volume_settings().model_dump(mode="python"),
            "cue_bindings": [
                {
                    "key": cue_key,
                    "asset_id": asset_id,
                    "asset_name": asset_name,
                    "asset_type": asset_type,
                    "asset_status": asset_status,
                    "gain_percent": gain_percent,
                }
                for cue_key, gain_percent, asset_id, asset_name, asset_type, asset_status in rows.all()
            ],
        }

    async def build_runtime_config(self, project: Project) -> dict[str, object]:
        """把项目音量与可用 cue 解析为 Runtime camelCase 快照。

        已归档、跨空间或非 audio 的历史绑定不会进入快照；声音不是页面导航的
        必要资源，缺绑定只表现为该 cue 静默，不阻塞预览或构建。
        """

        volume = load_audio_volume_settings(project.audio_settings_json)
        rows = await self.session.execute(
            select(
                ProjectAudioCueBinding.cue_key,
                ProjectAudioCueBinding.gain_percent,
                WorkspaceAsset.name,
            )
            .join(WorkspaceAsset, WorkspaceAsset.id == ProjectAudioCueBinding.asset_id)
            .where(ProjectAudioCueBinding.project_id == project.id)
            .where(WorkspaceAsset.workspace_id == project.workspace_id)
            .where(WorkspaceAsset.status == RecordStatus.ACTIVE.value)
            .where(WorkspaceAsset.asset_type == AssetType.AUDIO.value)
            .order_by(ProjectAudioCueBinding.cue_key)
        )
        resolved = [
            ResolvedAudioCueBinding(
                key=cue_key,
                asset_name=asset_name,
                gain_percent=gain_percent,
            )
            for cue_key, gain_percent, asset_name in rows.all()
        ]
        if not is_audio_capability_open(AUDIO_CAPABILITY_AUDIO_CUES):
            # 能力关闭时新快照不携带 cue；历史 artifact 不可变，不承诺全局停声。
            resolved = []
        return build_runtime_audio_config(volume, resolved)

    async def _replace_cues(
        self,
        project_id: int,
        bindings: Iterable[AudioCueBindingInput],
    ) -> None:
        """删除旧绑定并写入新集合；空集合表示显式清空。"""

        await self.session.execute(
            delete(ProjectAudioCueBinding).where(ProjectAudioCueBinding.project_id == project_id)
        )
        for binding in bindings:
            self.session.add(
                ProjectAudioCueBinding(
                    project_id=project_id,
                    cue_key=binding.key,
                    asset_id=binding.asset_id,
                    gain_percent=binding.gain_percent,
                )
            )

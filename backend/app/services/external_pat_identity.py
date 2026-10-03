"""文件功能：将严格认证后的 PAT ORM 记录适配为不持有存储记录的外部主体。"""

from app.models.api_access_token import ApiAccessToken
from app.services.external_principal import ExternalPrincipal, PatCredential


def principal_from_pat(token: ApiAccessToken) -> ExternalPrincipal:
    """复制已验证 PAT 的公共身份与权限；调用方必须先完成有效期、撤销和用户检查。"""

    return ExternalPrincipal(
        user=token.user,
        credential=PatCredential(
            token_id=token.id,
            public_id=token.token_public_id,
            name=token.name,
            expires_at=token.expires_at,
        ),
        all_workspaces=token.all_workspaces,
        workspace_ids=frozenset(workspace.workspace_id for workspace in token.workspaces),
        scopes=frozenset(scope.scope for scope in token.scopes),
    )

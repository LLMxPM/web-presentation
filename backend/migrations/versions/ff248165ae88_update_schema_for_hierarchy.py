"""update_schema_for_hierarchy

Revision ID: ff248165ae88
Revises: 20260328_0002
Create Date: 2026-03-28 15:45:50.630346

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ff248165ae88'
down_revision: Union[str, Sequence[str], None] = '20260328_0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('pages') as batch_op:
        batch_op.add_column(sa.Column('workspace_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('project_id', sa.Integer(), nullable=True))
        batch_op.create_index(op.f('ix_pages_project_id'), ['project_id'], unique=False)
        batch_op.create_index(op.f('ix_pages_workspace_id'), ['workspace_id'], unique=False)
        batch_op.create_foreign_key('fk_pages_project_id_projects', 'projects', ['project_id'], ['id'])
        batch_op.create_foreign_key('fk_pages_workspace_id_workspaces', 'workspaces', ['workspace_id'], ['id'])

    with op.batch_alter_table('workspaces') as batch_op:
        batch_op.add_column(sa.Column('last_opened_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('workspaces') as batch_op:
        batch_op.drop_column('last_opened_at')

    with op.batch_alter_table('pages') as batch_op:
        batch_op.drop_constraint('fk_pages_workspace_id_workspaces', type_='foreignkey')
        batch_op.drop_constraint('fk_pages_project_id_projects', type_='foreignkey')
        batch_op.drop_index(op.f('ix_pages_workspace_id'))
        batch_op.drop_index(op.f('ix_pages_project_id'))
        batch_op.drop_column('project_id')
        batch_op.drop_column('workspace_id')

"""remove persisted project icon config and add theme icon defaults

Revision ID: 20260417_0020
Revises: 20260417_0019
Create Date: 2026-04-17 20:10:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260417_0020"
down_revision: Union[str, Sequence[str], None] = "20260417_0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_ICON_CONFIG_YAML = """lucide_icons:
  - Menu
  - X
  - ChevronLeft
  - ChevronDown
  - ChevronRight
  - List
  - ArrowRight
  - Grid3x3
  - Home
  - BarChart3
  - Package
  - Layout
  - FileText
  - Monitor
  - ShoppingBag
  - Info
  - Square
  - Zap
  - BookOpen
  - Settings
  - Bug
  - Turtle
  - XCircle
  - Sidebar
  - Send
  - Cpu
  - Warehouse
  - Radio
  - Cable
  - Scan
  - ClipboardList
  - Bluetooth
  - Building
  - Car
  - UserCheck
  - Building2
  - CheckCircle
  - AlertTriangle
  - UserX
  - SearchX
  - Target
  - Smartphone
  - Shield
  - Package2
  - Unlink
  - Network
  - Quote
  - DollarSign
  - AlertCircle
  - Paintbrush
  - Palette
  - Type
  - FileImage
  - Compass
  - Users
  - Database
  - Globe
  - Code
  - Layers
  - Activity
  - Briefcase
  - Calendar
  - Clock
  - Download
  - Edit
  - Eye
  - Filter
  - Grid
  - Hash
  - Image
  - Link
  - Lock
  - Upload
  - Trash
  - Github
  - Mail
  - MapPin
  - Phone
  - MessageSquare
  - Search
  - Star
  - Tag
  - User
  - Video
  - Wifi
  - Wrench
  - Brain
  - MousePointer
  - Bot
  - Hammer
  - Lightbulb
  - Crown
  - Box
  - TrendingUp
  - GitBranch
  - Presentation
  - Maximize2
  - Minimize2
  - FileDown
  - Ampersand
  - TestTube
static_icons:
  - name: slider
    src: img/icon/slider.svg
  - name: c-search
    src: img/icon/search.svg
  - name: heart
    src: img/icon/heart.svg
  - name: star
    src: img/icon/star.svg
  - name: mail
    src: img/icon/mail.svg
  - name: 添加联系人
    src: img/icon/添加联系人.svg
  - name: 缩小
    src: img/icon/缩小.svg
  - name: home
    src: img/icon/home.svg
  - name: TOP榜
    src: img/icon/TOP榜.svg
  - name: 全屏
    src: img/icon/全屏.svg
  - name: 外汇
    src: img/icon/外汇.svg
  - name: 手电筒
    src: img/icon/手电筒.svg
  - name: 扫描
    src: img/icon/扫描.svg
  - name: 路由-copy
    src: img/icon/路由-copy.svg
  - name: 刷新
    src: img/icon/刷新.svg
config:
  default_size: 20
  default_stroke_width: 2
  fallback_behavior: show_placeholder
  placeholder_text: "?"
"""


def upgrade() -> None:
    """Upgrade schema."""

    with op.batch_alter_table("workspace_themes") as batch_op:
        batch_op.add_column(sa.Column("icon_default_size", sa.Integer(), nullable=False, server_default=sa.text("20")))
        batch_op.add_column(sa.Column("icon_default_stroke_width", sa.Integer(), nullable=False, server_default=sa.text("2")))

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("icon_config_yaml")


def downgrade() -> None:
    """Downgrade schema."""

    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("icon_config_yaml", sa.Text(), nullable=False, server_default=DEFAULT_ICON_CONFIG_YAML))

    with op.batch_alter_table("workspace_themes") as batch_op:
        batch_op.drop_column("icon_default_stroke_width")
        batch_op.drop_column("icon_default_size")

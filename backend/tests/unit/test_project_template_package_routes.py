"""文件功能：验证项目模板包路由层下载响应头等轻量辅助逻辑。"""

from __future__ import annotations

from app.api.routes.template_packages import build_template_package_content_disposition


def test_template_package_content_disposition_should_support_chinese_filename() -> None:
    """模板包下载响应头应使用 filename* 承载中文文件名。"""

    header = build_template_package_content_disposition("年度复盘.wptemplate.zip")

    header.encode("latin-1")
    assert 'filename="' in header
    assert "filename*=UTF-8''%E5%B9%B4%E5%BA%A6%E5%A4%8D%E7%9B%98.wptemplate.zip" in header

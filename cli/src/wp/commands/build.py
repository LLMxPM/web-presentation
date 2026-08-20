"""文件功能：处理项目静态构建任务触发、轮询与产物下载。"""

from __future__ import annotations

import click

from wp.client import ApiClient, ApiClientError
from wp.config import get_profile, load_config
from wp.formatter import print_error, print_json, print_success, print_table


@click.group("build")
def build_group() -> None:
    """项目静态整包构建任务。"""


@build_group.command("run")
@click.option("--project-id", "-p", required=True, type=int, help="项目 ID")
@click.option("--base-url", "-b", default="./", help="资源基准路径 (默认 ./)")
@click.option("--wait/--no-wait", default=True, help="是否等待构建完成 (默认等待)")
@click.pass_context
def run_build_cmd(ctx: click.Context, project_id: int, base_url: str, wait: bool) -> None:
    """提交项目整包静态构建发布任务。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        payload = {"base_url": base_url}
        job = client.post(f"/projects/{project_id}/builds", json_data=payload)
        job_id = job.get("id")
        print_success(f"构建任务已提交 (Job ID: [bold]{job_id}[/bold])")

        if not wait:
            if ctx.obj.get("as_json"):
                print_json(job)
            return

        with click.progressbar(length=100, label="正在执行多页面 Vite 生产构建与打包...") as bar:
            final_job = client.poll_build_job(job_id, timeout_seconds=180.0)
            bar.update(100)

        if final_job.get("status") == "succeeded":
            download_url = final_job.get("artifact_download_url") or final_job.get("artifact_proxy_url")
            print_success(f"项目构建成功！产物大小: {round(final_job.get('artifact_size_bytes', 0) / 1024, 1)} KB")
            if download_url:
                print_success(f"产物下载链接: [underline]{download_url}[/underline]")
        else:
            print_error(f"项目构建失败: {final_job.get('error_message')}")
            raise SystemExit(1)
    except ApiClientError as err:
        print_error(f"提交构建任务失败: {err.message}", code=err.code)
        raise SystemExit(1)


@build_group.command("status")
@click.argument("job_id", type=int)
@click.pass_context
def get_build_status_cmd(ctx: click.Context, job_id: int) -> None:
    """查询构建任务状态。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        job = client.get(f"/builds/{job_id}")
        if ctx.obj.get("as_json"):
            print_json(job)
            return

        rows = [
            ["ID", str(job.get("id"))],
            ["项目 ID", str(job.get("project_id"))],
            ["状态", str(job.get("status"))],
            ["产物大小", f"{round(job.get('artifact_size_bytes', 0) / 1024, 1)} KB" if job.get("artifact_size_bytes") else "-"],
            ["下载链接", str(job.get("artifact_download_url") or job.get("artifact_proxy_url") or "-")],
            ["创建时间", str(job.get("created_at"))],
        ]
        print_table(f"构建任务 (ID: {job_id}) 状态", ["属性", "值"], rows)
    except ApiClientError as err:
        print_error(f"查询构建状态失败: {err.message}", code=err.code)
        raise SystemExit(1)

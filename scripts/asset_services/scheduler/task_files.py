# 作用：管理任务临时工作目录，并只向调用方交付清单中的文件。
# 输入输出：working_directory(id) -> 临时路径；publish_output() -> 永久清单；remove_workspace() 删除中间文件。
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import uuid

from scheduler import task_queue


def working_directory(task_id: int) -> Path:
    """按数据库与任务 ID 定位跨阶段共用的系统临时目录。"""
    identity = hashlib.sha256(str(task_queue.DB_PATH.resolve()).casefold().encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / 'asset-services-new' / identity / str(task_id)


def publish_output(directory: Path, output_dir: str) -> dict | None:
    """只复制交付清单中的文件，完整复制后将结果目录一次性发布。"""
    manifest = directory / 'result.json'
    if not manifest.is_file():
        return None
    result = json.loads(manifest.read_text(encoding='utf-8'))
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f'交付目录已存在，禁止覆盖：{destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    paths = {}
    # 交付目录须继承项目父目录 ACL；TemporaryDirectory 的 0700 会隔离普通调用方。
    staging = destination.parent / ('.asset-delivery-' + uuid.uuid4().hex)
    staging.mkdir()
    try:
        for name, value in result['artifacts'].items():
            source = Path(value).resolve()
            relative = source.relative_to(directory.resolve())
            if not source.is_file() or source.stat().st_size == 0:
                raise RuntimeError(f'交付文件不存在或为空：{source}')
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            paths[name] = str(destination / relative)
        result['artifacts'] = paths
        (staging / 'result.json').write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        # 移动前确认暂存目录与明确指定的交付目录位于同一父目录。
        if staging.resolve().parent != destination.resolve().parent:
            raise RuntimeError('交付暂存路径越界')
        staging.rename(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return result


def remove_workspace(task_id: int) -> None:
    """验证目标仍是本服务的任务临时目录，再递归清理中间文件。"""
    directory = working_directory(task_id)
    if directory.resolve() != directory or directory.name != str(task_id):
        raise RuntimeError(f'拒绝清理发生重定向的临时路径：{directory}')
    if directory.exists():
        shutil.rmtree(directory)
    try:
        directory.parent.rmdir()
    except OSError:
        pass  # 其他任务仍在使用该数据库的临时目录。

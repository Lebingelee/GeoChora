# 数据库调用与数据结构定义。
# 输入输出：enqueue(steps, output_dir) -> 任务 ID；dequeue(resource) -> 已领取当前阶段的任务。
# 执行约定：领取后执行并 finish()，成功后推进下一阶段；不设跨进程资源锁。
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
import tempfile
from typing import Any, Literal, TypedDict

from common.service_config import DEPENDENCIES


DATA_DIR = DEPENDENCIES / 'data'
DB_PATH = DATA_DIR / 'tasks.sqlite3'
Resource = Literal['cpu', 'gpu']


class Step(TypedDict):
    """定义顺序执行阶段的资源类别与子进程启动参数。"""

    resource: Resource
    argv: list[str]


class Task(TypedDict):
    """保存阶段计划、当前阶段、调度状态及按执行顺序追加的结果。"""

    id: int
    steps: list[Step]
    current_step: int
    resource: Resource
    ready_order: int
    status: Literal['queued', 'running', 'succeeded', 'failed']
    result: list[dict[str, Any] | None]
    error: str | None
    output_dir: str | None
    output: dict[str, Any] | None


@contextmanager
def _connect():
    """打开短事务，正常退出提交、异常回滚，最后关闭连接。"""
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _decode(row) -> Task:
    """将数据库行中的 JSON 文本还原为阶段计划与执行结果。"""
    task = dict(row)
    task['steps'] = json.loads(task['steps'])
    task['result'] = json.loads(task['result'])
    task['output'] = json.loads(task['output']) if task['output'] else None
    return task


def _next_ready_order(connection) -> int:
    """在写事务内分配下一就绪序号，阶段切换后排在已就绪任务后面。"""
    return connection.execute('SELECT COALESCE(MAX(ready_order), 0) + 1 FROM tasks').fetchone()[0]


def initialize() -> None:
    """创建目录与任务表；重复调用保留全部已有任务。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        connection.execute('''CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            steps TEXT NOT NULL,
            current_step INTEGER NOT NULL DEFAULT 0,
            resource TEXT NOT NULL,
            ready_order INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            result TEXT NOT NULL DEFAULT '[]',
            error TEXT
        )''')

        columns = {row['name'] for row in connection.execute('PRAGMA table_info(tasks)')}
        for column in ('output_dir', 'output'):
            if column not in columns:
                connection.execute(f'ALTER TABLE tasks ADD COLUMN {column} TEXT')


def enqueue(steps: list[Step], output_dir: str) -> int:
    """保存非空的线性阶段列表，返回整个任务独立的 ID。"""
    if not isinstance(steps, list) or not steps:
        raise ValueError('steps 必须是非空的阶段列表')
    for step in steps:
        if not isinstance(step, dict) or step.get('resource') not in ('cpu', 'gpu'):
            raise ValueError('每个阶段的 resource 必须为 cpu 或 gpu')
        argv = step.get('argv')
        if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) for arg in argv):
            raise ValueError('每个阶段的 argv 必须是非空的字符串列表')
    destination = Path(output_dir)
    if not destination.is_absolute():
        raise ValueError('output_dir 必须为绝对路径')
    destination = destination.resolve()
    temporary_root = (Path(tempfile.gettempdir()) / 'asset-services-new').resolve()
    if destination.is_relative_to(DATA_DIR.resolve()) or destination.is_relative_to(temporary_root):
        raise ValueError('output_dir 必须位于服务 data 及任务临时目录之外')
    if destination.exists():
        raise ValueError('output_dir 必须是尚不存在的新目录，避免覆盖已有文件')
    steps_json = json.dumps(steps, ensure_ascii=False, allow_nan=False)
    with _connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        if connection.execute(
                "SELECT 1 FROM tasks WHERE output_dir = ? COLLATE NOCASE AND status IN ('queued','running')",
                (str(destination),)).fetchone():
            raise ValueError('output_dir 已被另一项待完成任务占用')
        cursor = connection.execute(
            'INSERT INTO tasks(steps, resource, ready_order, output_dir) VALUES (?, ?, ?, ?)',
            (steps_json, steps[0]['resource'], _next_ready_order(connection), str(destination)),
        )
        return cursor.lastrowid


def dequeue(resource: Resource) -> Task | None:
    """原子领取该资源最早就绪的阶段并标为 running；无就绪阶段返回 None。"""
    with _connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute(
            "SELECT * FROM tasks WHERE status='queued' AND resource=? ORDER BY ready_order LIMIT 1",
            (resource,),
        ).fetchone()
        if row is None:
            return None
        connection.execute("UPDATE tasks SET status='running' WHERE id=?", (row['id'],))
        task = _decode(row)
        task['status'] = 'running'
        return task


def finish(task_id: int, result: dict[str, Any] | None = None, error: str | None = None,
           output: dict[str, Any] | None = None) -> None:
    """保存当前阶段结果；成功则推进下一阶段，失败或最后一步结束整个任务。"""
    with _connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
        if row is None or row['status'] != 'running':
            raise ValueError(f'任务 {task_id} 不存在或未处于 running 状态')
        task = _decode(row)
        task['result'].append(result)
        status = 'succeeded' if error is None else 'failed'
        if error is None and task['current_step'] + 1 < len(task['steps']):
            task['current_step'] += 1
            task['resource'] = task['steps'][task['current_step']]['resource']
            task['ready_order'] = _next_ready_order(connection)
            status = 'queued'
        connection.execute(
            'UPDATE tasks SET current_step=?, resource=?, ready_order=?, status=?, result=?, error=?, output=? WHERE id=?',
            (task['current_step'], task['resource'], task['ready_order'], status,
             json.dumps(task['result'], ensure_ascii=False, allow_nan=False), error,
             json.dumps(output, ensure_ascii=False, allow_nan=False) if output is not None else None, task_id),
        )


def get_task(task_id: int) -> Task | None:
    """读取阶段计划、状态和结果；任务不存在返回 None。"""
    with _connect() as connection:
        row = connection.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
    return _decode(row) if row is not None else None


def wait_job(job_id: int) -> Task:
    """等待指定任务全部阶段成功或任一阶段失败；不存在的 ID 立即报错。"""
    while True:
        task = get_task(job_id)
        if task is None:
            raise ValueError(f'任务 {job_id} 不存在')
        if task['status'] in ('succeeded', 'failed'):
            return task
        time.sleep(0.25)

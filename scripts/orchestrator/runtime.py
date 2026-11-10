"""调度核心：进程池、并发闸门、状态库、控制协议。

架构（全部同机：MCP 服务 / codex / 实验产物 / 状态库）：
    ThreadPoolExecutor 等价物 = 多个 codex app-server 子进程
    调度 = 全局并发闸门（GLOBAL_MAX_PARALLEL）+ FIFO
    状态 = SQLite(WAL)；只存生命周期元数据，不存模型正文
    控制 = 本机 JSON 行协议（Windows 认证 loopback TCP，Linux Unix socket）

上下文隔离原则（本服务的核心约束）：
1. 原始终端事件只落盘到 events.jsonl，永不进 MCP 返回值。
2. 上行给总控 agent 的字段被 STATUS_FIELDS 白名单严格限制。
3. 裁决由 judge/断言在服务内部完成，只回传 verdict + ≤100 字理由。

重要函数：
- Store.add(manifest): 建批次并在磁盘铺设各 run 的独立 cwd。
- Daemon.run(run_id): 单 run 的完整生命周期（prepare -> thread/start -> turn -> 判定 -> 归档）。
- Daemon.request(operation, args): MCP 侧的唯一入口，返回白名单字段。
"""

import asyncio
import hashlib
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import yaml
from filelock import FileLock, Timeout

from . import ACTIVE, ERROR_CODES, TERMINAL, VERDICTS, Invalid
from .app_server import AppServer, BackendError, DEFAULT_SANDBOX

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 全局并发上限（用户设定）；judge 不占此配额。
GLOBAL_MAX_PARALLEL = 10

# worker 工作目录默认集中在忽略的 workspace/ 下，与服务代码目录分离。
CORE_ROOT = Path(__file__).resolve().parents[2]
REPO = os.environ.get("ORCHESTRATOR_REPO", str(CORE_ROOT / "workspace/scene-generation"))

# 调度状态根：与实验产物同机（NFS 上只放"大文件、要人看"的产物与日志）。
STATE = os.environ.get("ORCHESTRATOR_STATE", os.path.join(REPO, ".orchestrator"))

# 连接、数据库与独占锁必须位于支持文件锁的本地文件系统。
# NFS 等共享挂载可能无法正确协商文件锁，不能仅切换 SQLite journal_mode 规避。
# 用 STATE 的 hash 做子目录，保证多份部署（不同 ORCHESTRATOR_STATE）互不干扰。
RUNTIME = os.environ.get(
    "ORCHESTRATOR_RUNTIME",
    os.path.join(tempfile.gettempdir(), "orchestrator-" + hashlib.sha256(STATE.encode()).hexdigest()[:16]),
)

SOCKET = os.path.join(RUNTIME, "control.sock")
ENDPOINT = os.path.join(RUNTIME, "control.json")
DAEMON_LOCK = os.path.join(RUNTIME, "daemon.lock")
DAEMON_PID = os.path.join(RUNTIME, "daemon.pid")
STATE_DB = os.path.join(RUNTIME, "state.sqlite3")

# 日志与产物留在 NFS，方便人直接查看。
DAEMON_LOG = os.path.join(STATE, "daemon.log")

# skill 快照源：实验 cwd 里的 .agents 是真拷贝，冻结批次启动时的 skill 版本。
AGENTS_SOURCE = os.environ.get(
    "ORCHESTRATOR_AGENTS", str(CORE_ROOT / ".agents")
)

# run id / batch 内 name 的合法标识符。
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")

# 跨 MCP 边界允许返回的 run 字段白名单。绝不加入 thread_id / directory / prompt 等。
STATUS_FIELDS = ("id", "name", "attempt", "state", "error_code")

# 允许出现在 manifest run 条目里的键。
RUN_FIELDS = (
    "id",
    "directory",
    "model",
    "effort",
    "prompt",
    "images",
    "expect",
    "sandbox",
    "output_schema",
)

# 允许出现在 manifest 顶层的键。
MANIFEST_FIELDS = ("runs", "max_parallel", "judge", "agents_file")

# 默认注入的 outputSchema：强制 worker 自报成败，作为断言/judge 的输入源。
DEFAULT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["success", "failure"]},
        "artifacts": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["status", "artifacts", "reason"],
    "additionalProperties": False,
}

# worker 的默认模型与思考强度（用户指定，与开发用的 max 区分）。
DEFAULT_MODEL = "gpt-6-astra"
DEFAULT_EFFORT = "high"

# judge 用的廉价配置（受限预算）。
JUDGE_MODEL = "gpt-6-luna"
JUDGE_EFFORT = "low"
JUDGE_REASON_MAX_CHARS = 100

# wait_for_change 的允许范围（秒）。
WAIT_MIN_SECONDS = 1
WAIT_MAX_SECONDS = 86400

# 单次 turn 的现实时间上限：超时即中断并按 launch_interrupted 判失败。
TURN_TIMEOUT_SECONDS = float(os.environ.get("ORCHESTRATOR_TURN_TIMEOUT", 7200))

# 判定为会话建立失败、需要重试的 codex 错误码。
CODEX_RETRYABLE = ("stream_disconnected", "internal_error")


# ---------------------------------------------------------------------------
# 校验辅助
# ---------------------------------------------------------------------------

def code(condition, message):
    """条件为假时抛 Invalid(message)。"""
    if not condition:
        raise Invalid(message)


def identity(value):
    """校验标识符，返回原值；不合法抛 invalid_identifier。"""
    if not isinstance(value, str) or not IDENTIFIER.match(value):
        raise Invalid("invalid_identifier")
    return value


def repo_file(value, directory=False):
    """把仓库相对路径解析为绝对路径，并确保未越出 REPO。

    允许目标尚不存在（run 的 directory 正是待创建的），但必须确实落在 REPO 内。
    符号链接按 realpath 消解后再判边界，因此指向仓库外的软链会被拒。
    """
    code(isinstance(value, str) and value.strip(), "invalid_input_path")
    root = Path(REPO).resolve()
    path = Path(value)
    if not path.is_absolute():
        path = root / path

    # 逐段解析：存在的部分走 realpath（消解软链），不存在的尾部按字面拼接。
    resolved = Path(os.path.realpath(path))
    if not resolved.is_relative_to(root):
        raise Invalid("input_outside_repository")

    if not resolved.exists():
        raise Invalid("input_not_found")
    if directory and not resolved.is_dir():
        raise Invalid("input_not_found")
    return resolved


def repo_path(value):
    """解析**允许尚不存在**的仓库内路径（run 的目标 directory）。

    与 repo_file 的唯一差别：不要求存在。符号链接按 realpath 消解后仍须落在 REPO 内。
    """
    code(isinstance(value, str) and value.strip(), "invalid_input_path")
    root = Path(REPO).resolve()
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    resolved = Path(os.path.realpath(path))
    if not resolved.is_relative_to(root):
        raise Invalid("input_outside_repository")
    return resolved


def load_manifest(value):
    """读取并校验 manifest YAML，返回标准化后的 dict。

    Args:
        value: 仓库相对（或绝对，但须在 REPO 内）的 YAML 路径。

    Returns:
        {"path": 绝对路径, "max_parallel": int, "judge": dict,
         "agents_file": str|None, "runs": [标准化 run dict, ...]}

    Raises:
        Invalid: 路径越界/不存在/YAML 破损/字段未知/并发上限非法/id 重复/目录已存在。
    """
    path = repo_file(value)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        raise Invalid("invalid_manifest")
    if not isinstance(raw, dict):
        raise Invalid("invalid_manifest")

    for key in raw:
        if key not in MANIFEST_FIELDS:
            raise Invalid("unknown_manifest_field")

    max_parallel = raw.get("max_parallel", GLOBAL_MAX_PARALLEL)
    if not isinstance(max_parallel, int) or isinstance(max_parallel, bool) or max_parallel < 1:
        raise Invalid("invalid_parallel_limit")
    if max_parallel > GLOBAL_MAX_PARALLEL:
        raise Invalid("invalid_parallel_limit")

    runs_raw = raw.get("runs")
    if not isinstance(runs_raw, list) or not runs_raw:
        raise Invalid("invalid_manifest")

    seen = set()
    runs = []
    for entry in runs_raw:
        if not isinstance(entry, dict):
            raise Invalid("invalid_manifest")
        for key in entry:
            if key not in RUN_FIELDS:
                raise Invalid("invalid_run_fields")
        name = identity(entry.get("id"))
        if name in seen:
            raise Invalid("duplicate_run_id")
        seen.add(name)

        directory = entry.get("directory")
        if directory is None:
            raise Invalid("invalid_directory")
        resolved_dir = repo_path(directory)
        # 目标目录必须尚不存在：存在即为重名冲突，避免覆盖已有实验。
        if resolved_dir.exists():
            raise Invalid("directory_already_exists")

        model = entry.get("model") or DEFAULT_MODEL
        effort = entry.get("effort") or DEFAULT_EFFORT
        if not isinstance(model, str) or not isinstance(effort, str):
            raise Invalid("invalid_run_fields")

        prompt = entry.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise Invalid("invalid_run_fields")

        images_raw = entry.get("images") or []
        if not isinstance(images_raw, list) or not all(isinstance(i, str) for i in images_raw):
            raise Invalid("invalid_run_fields")
        images = [str(repo_file(i)) for i in images_raw]

        expect_raw = entry.get("expect") or []
        if not isinstance(expect_raw, list) or not all(isinstance(i, str) for i in expect_raw):
            raise Invalid("invalid_run_fields")

        sandbox = entry.get("sandbox") or DEFAULT_SANDBOX
        if sandbox not in ("read-only", "workspace-write", "danger-full-access"):
            raise Invalid("invalid_run_fields")

        schema = entry.get("output_schema")
        if schema is None:
            schema = DEFAULT_OUTPUT_SCHEMA
        validate_output_schema(schema)

        runs.append({
            "id": name,
            "directory": str(resolved_dir),
            "model": model,
            "effort": effort,
            "prompt": prompt,
            "images": images,
            "expect": list(expect_raw),
            "sandbox": sandbox,
            "output_schema": schema,
        })

    judge_cfg = raw.get("judge") or {}
    if not isinstance(judge_cfg, dict):
        raise Invalid("invalid_manifest")

    return {
        "path": str(path),
        "max_parallel": max_parallel,
        "judge": judge_cfg,
        "agents_file": raw.get("agents_file"),
        "runs": runs,
    }


def _strict_schema_problem(node, path=""):
    """按 OpenAI strict structured-output 规则检查一个 schema 节点。

    实测（codex 0.160.0 服务端条文，报错文本逐条对应）：
    - 根必须是 type=object。
    - 每个 object 节点都必须同时给出 properties / required / additionalProperties=false，
      且 required 恰为 properties 的键集（少一个即 400）。
    - 数组的 items 同样递归受检。

    返回错误串（含出错 JSON 路径），合规返回 None。
    """
    if not isinstance(node, dict):
        return "schema node is not an object"

    ref = node.get("$ref")
    if isinstance(ref, str):
        if not ref.startswith("#/"):
            return f"{path}: $ref must be a local JSON pointer"
        # 本轮 $defs / definitions 的误报不足以支撑整表拒绝，交回服务端判定。
        return None

    node_type = node.get("type")
    if node_type is None:
        return f"In context={path}, 'type' is required to be supplied"
    if path == "" and node_type != "object":
        # 实测服务端：schema must be a JSON Schema of 'type: "object"'。
        return f"root schema must be type: object, got {node_type!r}"

    if node_type == "object":
        where = f"schema{path}"
        props = node.get("properties")
        if not isinstance(props, dict):
            return f"{where}.properties is required for object schemas"
        required = node.get("required")
        if not isinstance(required, list):
            return f"In context={path}, 'required' is required to be supplied and to be an array"
        for req_key in required:
            if req_key not in props:
                return f"{where}.required' includes extra key '{req_key}'"
        for prop_key in props:
            if prop_key not in required:
                return f"{where}.required' is required to include '{prop_key}'"
        if node.get("additionalProperties") is not False:
            return f"{where}.additionalProperties is required to be false"
        for prop_key, child in props.items():
            problem = _strict_schema_problem(child, f"{path}/properties/{prop_key}")
            if problem:
                return problem
        return None

    if node_type == "array":
        if "items" not in node:
            return f"{path}: arrays require 'items'"
        return _strict_schema_problem(node["items"], f"{path}/items")

    if isinstance(node_type, str) and node_type != "null":
        return None

    return f"{path}: unsupported type {node_type!r}"


def validate_output_schema(schema):
    """本地预校验 outputSchema。

    必须在这里失败，而不是让 turn 异步失败——实测非法 schema 约 3.5s 后
    才以 invalid_json_schema 报错，与普通任务失败无法区分。

    两道关：
    1. jsonschema 元模式校验，拦住 type 拼写错误、enum 非数组这类结构性错误。
    2. strict 规则校验，拦住能通过元模式、但服务端 400 的形状
       （如 required 缺失属性却配 additionalProperties:false）。
    """
    import jsonschema

    if not isinstance(schema, dict):
        raise Invalid("invalid_output_schema")
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except jsonschema.SchemaError:
        raise Invalid("invalid_output_schema")
    if _strict_schema_problem(schema):
        raise Invalid("invalid_output_schema")


# ---------------------------------------------------------------------------
# 状态库
# ---------------------------------------------------------------------------

# WAL 只在这些本地文件系统上安全；其余（nfs/nfs4/cifs/fuse/ceph/glusterfs…）一律禁用。
WAL_SAFE_FILESYSTEMS = ("ext4", "ext3", "ext2", "xfs", "btrfs", "tmpfs", "overlay", "zfs", "ntfs")


def _mount_type(path):
    """返回 path 所在挂载点的文件系统类型；查不到返回空串。"""
    if os.name == "nt":
        import ctypes
        anchor = Path(path).resolve().anchor
        return "ntfs" if ctypes.windll.kernel32.GetDriveTypeW(anchor) == 3 else ""
    try:
        target = os.path.realpath(str(path))
        best, best_type = "", ""
        with open("/proc/mounts", encoding="utf-8") as handle:
            for line in handle:
                parts = line.split()
                if len(parts) < 3:
                    continue
                mount, fstype = parts[1], parts[2]
                # 取最长匹配的挂载点，避免 /opt 覆盖 /opt/data 这类前缀误判。
                if (target == mount or target.startswith(mount.rstrip("/") + "/")) \
                        and len(mount) >= len(best):
                    best, best_type = mount, fstype
        return best_type
    except OSError:
        return ""


def _is_local_fs(path):
    """判断 path 是否在本地文件系统上（NFS 上 sqlite/flock 会永久挂起）。"""
    return _mount_type(path) in WAL_SAFE_FILESYSTEMS


def _supports_wal(path):
    """判断 path 所在文件系统是否支持 WAL（NFS 上设 WAL 会永久挂起）。"""
    # 读不到挂载表时 _mount_type 返回空串，不在白名单内 → 保守禁用 WAL。
    return _mount_type(path) in WAL_SAFE_FILESYSTEMS


class Store:
    """SQLite(WAL) 状态库。只保存生命周期元数据，不含模型正文。

    重要函数：
    - add(manifest): 建批次、铺目录、写入 queued 记录，返回 (batch_id, run_ids)。
    - snapshot(batch_id): 返回批次 revision 与各 run 的白名单字段。
    - retry(run_id): 用冻结输入创建新目录与新会话，不读取旧历史。
    """

    def __init__(self, state=STATE, database=None):
        """state: 产物/日志根（可在 NFS）；database: 库文件路径（必须本地盘）。"""
        self.state = Path(state)
        self.state.mkdir(parents=True, exist_ok=True)
        # ⚠️ 库文件必须落在**本地文件系统**：NFS( local_lock=none ) 上 sqlite 的
        # 任何写操作（哪怕 CREATE TABLE）都会永久阻塞，因为它拿不到 POSIX 锁。
        # 换 journal_mode 无效（DELETE/WAL 都要锁）。详见 RUNTIME 处的实测说明。
        if database is None:
            database = STATE_DB
            target = Path(database).parent
            if not _is_local_fs(target):
                # 兜底：万一 RUNTIME 也被指到 NFS，退到 /tmp 以免 daemon 无声挂死。
                database = os.path.join(tempfile.gettempdir(), "orchestrator-state-" + hashlib.sha256(STATE.encode()).hexdigest()[:16] + ".sqlite3")
        Path(database).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(database)
        self.connection = sqlite3.connect(self.path, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        # 锁等待上限：本地盘上多进程竞争时避免无限等待。
        self.connection.execute("PRAGMA busy_timeout=30000")
        if _supports_wal(Path(self.path).parent):
            self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS batches (
                id TEXT PRIMARY KEY,
                max_parallel INTEGER NOT NULL,
                revision INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                name TEXT NOT NULL,
                attempt INTEGER NOT NULL DEFAULT 1,
                state TEXT NOT NULL,
                spec TEXT NOT NULL,
                directory TEXT NOT NULL,
                thread_id TEXT,
                turn_id TEXT,
                error_code TEXT,
                verdict TEXT,
                verdict_reason TEXT,
                artifacts TEXT,
                created REAL NOT NULL,
                updated REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS runs_batch ON runs(batch_id);
            CREATE INDEX IF NOT EXISTS runs_state ON runs(state);
            """
        )

    def row(self, run_id):
        """返回 run 的完整行（含 thread_id 等内部字段，仅供本服务内部使用）。"""
        found = self.connection.execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
        if found is None:
            raise Invalid("unknown_run")
        return dict(found)

    def batch_row(self, batch_id):
        """返回批次的完整行。"""
        found = self.connection.execute(
            "SELECT * FROM batches WHERE id = ?", (batch_id,)
        ).fetchone()
        if found is None:
            raise Invalid("unknown_batch")
        return dict(found)

    def update(self, run_id, **fields):
        """更新字段并递增所属批次 revision，随后唤醒 wait 等待者。"""
        current = self.row(run_id)
        allowed = {
            "state", "thread_id", "turn_id", "error_code", "verdict",
            "verdict_reason", "artifacts", "directory", "spec", "attempt",
        }
        columns, values = [], []
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"illegal column {key}")
            if key == "artifacts" and value is not None:
                value = json.dumps(list(value))
            columns.append(f"{key} = ?")
            values.append(value)
        columns.append("updated = ?")
        values.append(time.time())
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                f"UPDATE runs SET {', '.join(columns)} WHERE id = ?",
                (*values, run_id),
            )
            self.connection.execute(
                "UPDATE batches SET revision = revision + 1 WHERE id = ?",
                (current["batch_id"],),
            )
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def bump(self, batch_id):
        """仅递增批次 revision（用于强制唤醒 wait 等待者）。"""
        self.connection.execute(
            "UPDATE batches SET revision = revision + 1 WHERE id = ?", (batch_id,)
        )

    def snapshot(self, batch_id):
        """返回 {revision, counts, runs:[白名单字段]}。"""
        batch = self.batch_row(batch_id)
        rows = self.connection.execute(
            "SELECT * FROM runs WHERE batch_id = ? ORDER BY created, id", (batch_id,)
        ).fetchall()
        counts = {}
        listed = []
        for row in rows:
            counts[row["state"]] = counts.get(row["state"], 0) + 1
            listed.append({field: row[field] for field in STATUS_FIELDS})
        return {
            "batch_id": batch_id,
            "revision": batch["revision"],
            "counts": counts,
            "runs": listed,
        }

    def list_batches(self, limit=100):
        """返回最近 limit 个批次的编号/状态/计数（不含 run 明细）。"""
        rows = self.connection.execute(
            "SELECT * FROM batches ORDER BY rowid DESC LIMIT ?", (limit,)
        ).fetchall()
        listed = []
        for batch in rows:
            counts = {}
            for row in self.connection.execute(
                "SELECT state, COUNT(*) AS n FROM runs WHERE batch_id = ? GROUP BY state",
                (batch["id"],),
            ):
                counts[row["state"]] = row["n"]
            listed.append({
                "batch_id": batch["id"],
                "revision": batch["revision"],
                "counts": counts,
            })
        return {"batches": listed}

    def add(self, manifest):
        """见类 docstring。铺设内容包括 prompt/图片快照与 .agents 真拷贝。"""
        batch_id = "batch_" + uuid.uuid4().hex
        created = time.time()
        self.connection.execute(
            "INSERT INTO batches (id, max_parallel, revision) VALUES (?, ?, 0)",
            (batch_id, manifest.get("max_parallel", GLOBAL_MAX_PARALLEL)),
        )
        run_ids = []
        made = []
        try:
            for spec in manifest["runs"]:
                run_id = "run_" + uuid.uuid4().hex
                row = {
                    "id": run_id,
                    "batch_id": batch_id,
                    "name": spec["id"],
                    "attempt": 1,
                    "state": "queued",
                    "spec": json.dumps(spec),
                    "directory": spec["directory"],
                }
                prepare(row)
                made.append(spec["directory"])
                self.connection.execute(
                    """INSERT INTO runs
                       (id, batch_id, name, attempt, state, spec, directory,
                        created, updated)
                       VALUES (?, ?, ?, 1, 'queued', ?, ?, ?, ?)""",
                    (run_id, batch_id, spec["id"], row["spec"],
                     spec["directory"], created, created),
                )
                run_ids.append(run_id)
        except BaseException:
            # 铺目录失败必须回滚，避免留下半成品目录与空 run。
            for directory in made:
                shutil.rmtree(directory, ignore_errors=True)
            self.connection.execute("DELETE FROM runs WHERE batch_id = ?", (batch_id,))
            self.connection.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
            raise
        return batch_id, run_ids

    def retry(self, run_id):
        """见类 docstring；仅允许对最新一次尝试重试。"""
        old = self.row(run_id)
        if old["state"] not in TERMINAL:
            raise Invalid("run_not_finished")
        newest = self.connection.execute(
            "SELECT MAX(attempt) AS n FROM runs WHERE batch_id = ? AND name = ?",
            (old["batch_id"], old["name"]),
        ).fetchone()["n"]
        if old["attempt"] != newest:
            raise Invalid("retry_latest_attempt_only")

        # 冻结输入：只用 spec 里已保存的内容，不读旧目录、不读历史正文。
        spec = json.loads(old["spec"])
        spec["directory"] = spec["directory"] + "_retry" + (
            "" if old["attempt"] == 1 else str(old["attempt"])
        )
        validate_output_schema(spec.get("output_schema"))
        new_id = "run_" + uuid.uuid4().hex
        row = {
            "id": new_id,
            "batch_id": old["batch_id"],
            "name": old["name"],
            "attempt": old["attempt"] + 1,
            "state": "queued",
            "spec": json.dumps(spec),
            "directory": spec["directory"],
        }
        prepare(row)
        now = time.time()
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                """INSERT INTO runs
                   (id, batch_id, name, attempt, state, spec, directory,
                    created, updated)
                   VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?)""",
                (new_id, old["batch_id"], old["name"], row["attempt"],
                 row["spec"], spec["directory"], now, now),
            )
            self.connection.execute(
                "UPDATE batches SET revision = revision + 1 WHERE id = ?",
                (old["batch_id"],),
            )
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            shutil.rmtree(spec["directory"], ignore_errors=True)
            raise
        return new_id, old["batch_id"], row["attempt"]

    def set_verdict(self, run_id, verdict, reason, artifacts):
        """写入裁决结果（verdict ∈ VERDICTS），供归档与 MCP 读取。"""
        if verdict not in VERDICTS:
            raise Invalid("invalid_manifest")
        text = (reason or "")[:JUDGE_REASON_MAX_CHARS]
        self.update(run_id, verdict=verdict, verdict_reason=text,
                    artifacts=list(artifacts or []))

    def queued(self, limit):
        """按 FIFO 取最多 limit 个 queued run（跨批次）。"""
        rows = self.connection.execute(
            "SELECT * FROM runs WHERE state = 'queued' ORDER BY created, id LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# 目录铺设
# ---------------------------------------------------------------------------

def snapshot_agents(dest):
    """把 AGENTS_SOURCE 真拷贝到 dest，返回指纹 dict（git_commit/dirty/skill_hashes）。"""
    source = Path(AGENTS_SOURCE)
    dest_path = Path(dest)
    if dest_path.exists():
        shutil.rmtree(dest_path, ignore_errors=True)
    if source.is_dir():
        # 必须真拷贝：NFS 上硬链接无法冻结 skill（open('w') 穿透共享 inode）。
        shutil.copytree(
            source, dest_path,
            ignore=shutil.ignore_patterns("__pycache__"),
            symlinks=True,
        )
    else:
        dest_path.mkdir(parents=True, exist_ok=True)

    def git_output(args):
        """读取 Skill 来源的 Git 身份，读取失败时返回空值。"""
        try:
            done = subprocess.run(
                ["git", *args], cwd=str(source), capture_output=True,
                text=True, encoding="utf-8", timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if done.returncode != 0:
            return None
        return done.stdout

    commit = git_output(["rev-parse", "HEAD"])
    status = git_output(["status", "--porcelain"])
    dirty = None if status is None else bool(status.strip())

    skill_hashes = {}
    skills = dest_path / "skills"
    if skills.is_dir():
        for skill in sorted(skills.iterdir()):
            skill_file = skill / "SKILL.md"
            if skill.is_dir() and skill_file.is_file():
                digest = hashlib.sha256(skill_file.read_bytes()).hexdigest()
                skill_hashes[skill.name] = digest

    if dirty:
        print(f"[orchestrator] 警告：.agents 源仓存在未提交改动（dirty=true），"
              f"快照仍被冻结为 {commit or 'unknown'}", flush=True)

    return {
        "source": str(source),
        "git_commit": commit.strip() if commit else None,
        "dirty": dirty,
        "skill_hashes": skill_hashes,
    }


def prepare(row):
    """为单个 run 铺设独立 cwd。

    实测约束：
    - .agents 必须是**真拷贝**（硬链接在 NFS 上无法冻结：python open('w')
      会穿透共享 inode；reflink 在 NFS 上不支持）。
    - 记录 skill 快照指纹（git_commit / dirty / 各 skill 哈希）到 meta.json；
      dirty 时仅警告，不阻塞。
    - 图片与 prompt 一律复制快照，不用符号链接。

    返回该 run 的工作目录绝对路径。
    """
    spec = json.loads(row["spec"])
    cwd = Path(spec["directory"])
    cwd.mkdir(parents=True, exist_ok=True)

    inputs = cwd / ".experiment-input"
    images_dir = inputs / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    (inputs / "prompt.txt").write_text(spec["prompt"], encoding="utf-8")

    copied_images = []
    for image in spec.get("images", []):
        origin = Path(image)
        if not origin.is_file():
            raise Invalid("input_not_found")
        target = images_dir / origin.name
        shutil.copy2(origin, target)
        copied_images.append(str(target))

    fingerprint = snapshot_agents(cwd / ".agents")
    if spec.get("agents_file"):
        source_agents = repo_file(spec["agents_file"])
        shutil.copy2(source_agents, cwd / "AGENTS.md")
    else:
        (cwd / "AGENTS.md").write_text(
            "# 实验会话\n\n"
            "本目录是一个独立的实验工作区。请遵循 .agents/skills 下的技能说明，"
            "在当前目录内完成 .experiment-input/prompt.txt 描述的任务。\n\n"
            f"本次工具与仓库文档根目录：`{CORE_ROOT}`。\n"
            "Skill 中指向仓库 docs/、scripts/、task_env/ 的相对链接从该根目录解析；"
            "生成文件仍写入当前工作区。\n",
            encoding="utf-8",
        )

    meta = {
        "run_id": row["id"],
        "batch_id": row["batch_id"],
        "name": row["name"],
        "attempt": row["attempt"],
        "prompt": spec["prompt"],
        "images": copied_images,
        "expect": spec.get("expect", []),
        "model": spec["model"],
        "effort": spec["effort"],
        "agents": fingerprint,
        "prepared": time.time(),
    }
    (cwd / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return str(cwd)


def archive(run_id, verdict, artifacts):
    """按裁决结果归档：archive/<batch>/success|failed/<run>/。

    归档内容为 verdict.json + 人可读 .md + 指向产物的符号链接，
    不搬运产物本体。
    """
    store = shared_store()
    row = store.row(run_id)
    spec = json.loads(row["spec"])
    reason = row.get("verdict_reason") or ""
    latest = artifacts if artifacts is not None else json.loads(row.get("artifacts") or "[]")

    bucket = "success" if verdict == "pass" else "failed"
    target = Path(STATE) / "archive" / row["batch_id"] / bucket / run_id
    target.mkdir(parents=True, exist_ok=True)

    (target / "verdict.json").write_text(
        json.dumps({
            "run_id": run_id,
            "name": row["name"],
            "attempt": row["attempt"],
            "state": row["state"],
            "verdict": verdict,
            "reason": reason,
            "artifacts": list(latest),
        }, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    lines = [
        f"# {row['name']} ({run_id})",
        "",
        f"- 批次：`{row['batch_id']}`",
        f"- 第 {row['attempt']} 次尝试",
        f"- 状态：`{row['state']}`",
        f"- 裁决：**{verdict}**",
        f"- 理由：{reason or '（无）'}",
        f"- 工作目录：`{spec.get('directory') or row['directory'] or '（未知）'}`",
        "",
        "## 任务",
        "",
        spec.get("prompt") or "（无）",
        "",
        "## 产物",
        "",
    ]
    for artifact in latest:
        lines.append(f"- `{artifact}`")
    if not latest:
        lines.append("- （worker 未申报任何产物）")
    (target / f"{run_id}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    links = target / "artifacts"
    if latest:
        links.mkdir(exist_ok=True)
        for index, artifact in enumerate(latest):
            origin = Path(artifact)
            if not origin.is_absolute():
                origin = Path(spec.get("directory") or row["directory"] or ".") / origin
            link = links / f"{index:03d}_{origin.name}"
            try:
                if link.is_symlink() or link.exists():
                    link.unlink()
                # 悬空软链是允许的：产物可能已被 worker 删除。
                link.symlink_to(origin)
            except OSError:
                continue
    return str(target)


_SHARED_STORE = None
"""进程内共享的 Store；archive() 是无 store 参数的模块级函数，需一个落点。"""


def shared_store(store=None):
    """取进程内共享 Store；未设置时惰性建一个默认实例。"""
    global _SHARED_STORE
    if store is not None:
        _SHARED_STORE = store
    if _SHARED_STORE is None:
        _SHARED_STORE = Store()
    return _SHARED_STORE


# ---------------------------------------------------------------------------
# 调度器
# ---------------------------------------------------------------------------

class Daemon:
    """常驻调度进程。持有多个 codex app-server，按全局闸门派发 run。

    重要函数：
    - schedule(): 主循环，取 queued run 填满并发闸门，回收已完成任务。
    - run(run_id): 单 run 生命周期；所有模型输出在内部消化，不向上泄露。
    - request(operation, args): MCP 唯一入口，返回白名单字段。
    """

    def __init__(self, store, command=None, max_parallel=GLOBAL_MAX_PARALLEL):
        """store: 状态库；command: codex argv；max_parallel: 全局闸门（默认 10）。"""
        self.store = shared_store(store)
        self.command = command or [
            os.environ.get("ORCHESTRATOR_CODEX", shutil.which("codex") or "codex"),
            "app-server", "--stdio",
        ]
        self.max_parallel = min(max_parallel, GLOBAL_MAX_PARALLEL)

        self.tasks = {}           # run_id -> asyncio.Task
        self.by_thread = {}       # thread_id -> run_id（event sink 用它找 run）
        self.backends = {}        # run_id -> AppServer
        self.batch_of = {}        # run_id -> batch_id（执行批次级 max_parallel）
        self.finished = {}        # run_id -> self_report（worker 自报，仅内部）
        self.tokens = {}          # run_id -> totalTokens（只留计数）
        self._pending_completion = {}  # turn_id -> {status, error_code}
        self.waiter = asyncio.Condition()
        self.model_cache = {}     # batch_id -> model/list 目录
        self.server = None
        self.schedule_task = None
        self.shutting_down = False

    # -- 事件与通知 ------------------------------------------------------

    def events_path(self, run_id):
        """run 的原始事件审计落盘位置。"""
        row = self.store.row(run_id)
        return Path(STATE) / "runs" / row["batch_id"] / row_id_folder(row) / "events.jsonl"

    def event(self, message):
        """codex 通知的 sink。原始事件 append 到 events.jsonl，提取白名单字段更新状态。"""
        thread_id = (message.get("params") or {}).get("threadId")
        run_id = self.by_thread.get(thread_id)
        if run_id is None:
            # 通知没有 jsonrpc 字段；无法归因的报文只落盘不解析。
            return
        try:
            path = self.events_path(run_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(message, ensure_ascii=False) + "\n")
        except (OSError, Invalid):
            return

        method = message.get("method")
        params = message.get("params") or {}
        if method == "turn/completed":
            turn = params.get("turn") or {}
            turn_id = turn.get("id")
            if turn_id:
                self._pending_completion[turn_id] = {
                    "status": turn.get("status"),
                    "error_code": self.error_code_of(turn.get("error")),
                }
            # 自报正文只在本进程内存里解析出三个白名单字段，随即丢弃原文：
            # status/artifacts/reason 用于判定，绝不写入 DB、绝不跨 MCP 边界。
            self.finished[run_id] = self.parse_self_report(turn)
        elif method == "thread/tokenUsage/updated":
            usage = (params.get("tokenUsage") or {}).get("total") or {}
            tokens = usage.get("totalTokens")
            if isinstance(tokens, int):
                # 只留一个计数，不进 DB 正文。
                self.tokens[run_id] = tokens

    def parse_self_report(self, turn):
        """从 turn 的 agentMessage 里解析 worker 自报；解析不出即视为 failure。

        outputSchema 已强制 worker 回 JSON；但 worker 仍可能回散文或半截 JSON，
        这里只认严格的 dict 形态，其余一律当 failure（保守，避免假成功）。
        """
        chunks = []
        for item in turn.get("items") or []:
            if isinstance(item, dict) and item.get("type") == "agentMessage":
                chunks.append(item.get("text") or "")
        text = "\n".join(chunks).strip()
        if not text:
            return {"status": "failure", "artifacts": [], "reason": "worker 无输出"}
        try:
            value = json.loads(text)
        except ValueError:
            return {"status": "failure", "artifacts": [], "reason": "worker 输出非 JSON"}
        if not isinstance(value, dict):
            return {"status": "failure", "artifacts": [], "reason": "worker 输出非 JSON 对象"}
        status = value.get("status")
        artifacts = value.get("artifacts")
        reason = value.get("reason")
        if status not in ("success", "failure"):
            return {"status": "failure", "artifacts": [], "reason": "worker 自报 status 非法"}
        if not isinstance(artifacts, list):
            artifacts = []
        return {
            "status": status,
            "artifacts": [str(a) for a in artifacts if isinstance(a, str)],
            "reason": str(reason or "")[:JUDGE_REASON_MAX_CHARS],
        }

    def error_code_of(self, error):
        """把 turn.error 解析成预定义 code；message 是再包一层的 JSON 字符串。"""
        if not error:
            return None
        raw = error.get("message") if isinstance(error, dict) else str(error)
        text = ""
        if isinstance(raw, str):
            try:
                inner = json.loads(raw)
                text = str(((inner.get("error") or {}).get("message")) or raw)
                inner_code = (inner.get("error") or {}).get("code")
                if inner_code:
                    text = f"{inner_code} {text}"
            except (ValueError, AttributeError):
                text = raw
        else:
            text = str(raw)
        lowered = text.lower()
        if "invalid_json_schema" in lowered:
            return "invalid_output_schema"
        if "model is not supported" in lowered or "model_not_found" in lowered:
            return "model_not_in_catalog"
        if "stream_disconnected" in lowered or "stream disconnected" in lowered:
            return "backend_disconnected"
        if "launch" in lowered and "interrupt" in lowered:
            return "launch_interrupted"
        return "backend_disconnected"

    def notify(self):
        """唤醒所有 wait_for_change 等待者。"""
        async def wake():
            """唤醒等待当前批次状态变化的连接。"""
            async with self.waiter:
                self.waiter.notify_all()
        return wake()

    # -- 后端 ------------------------------------------------------------

    async def backend(self, run_id):
        """为 run 取（或新建）一个 AppServer 实例。"""
        existing = self.backends.get(run_id)
        if existing is not None:
            return existing
        row = self.store.row(run_id)
        stderr_path = Path(STATE) / "runs" / row["batch_id"] / row_id_folder(row) / "logs" / "codex.stderr.log"
        stderr_path.parent.mkdir(parents=True, exist_ok=True)

        run_id_box = {"value": run_id}

        def sink(message):
            """将后端通知归属到当前会话并交给事件处理器。"""
            # 闭包捕获 thread 映射：先按 threadId 归因，回过味来再修正。
            if run_id_box["value"] is None:
                thread_id = (message.get("params") or {}).get("threadId")
                run_id_box["value"] = self.by_thread.get(thread_id)
            if run_id_box["value"]:
                self.event(message)

        server = AppServer(self.command, sink, stderr_path=str(stderr_path))
        await server.start()
        self.backends[run_id] = server
        return server

    async def validate_models(self, manifest):
        """用 model/list 预校验 model / effort / 图片能力。

    绝不依赖 turn 异步失败来发现非法模型。
        """
        probe = AppServer(self.command, lambda message: None)
        await probe.start()
        try:
            catalog = {item.get("model"): item for item in await probe.models()}
        finally:
            await probe.close()
        for spec in manifest["runs"]:
            entry = catalog.get(spec["model"])
            if entry is None:
                raise Invalid("model_not_in_catalog")
            efforts = [
                item.get("reasoningEffort")
                for item in (entry.get("supportedReasoningEfforts") or [])
            ]
            if spec["effort"] not in efforts:
                raise Invalid("unsupported_reasoning_effort")
            if spec.get("images"):
                if "image" not in (entry.get("inputModalities") or []):
                    raise Invalid("model_does_not_support_images")
        return catalog

    # -- 单 run 生命周期 -------------------------------------------------

    async def run(self, run_id):
        """单 run 完整生命周期。

        步骤：prepare -> thread/start -> turn/start -> 等 turn/completed
              -> 断言检查 -> （必要时）judge -> 写 verdict -> 归档。
        worker 的正文、推理、日志一律不进入返回值。
        """
        row = self.store.row(run_id)
        spec = json.loads(row["spec"])
        server = None
        try:
            # prepare 已在 Store.add 时完成；此处只确认目录仍在。
            self.store.update(run_id, state="starting")
            server = await self.backend(run_id)
            started = await server.call("thread/start", {
                "cwd": spec["directory"],
                "model": spec["model"],
                "config": {"model_reasoning_effort": spec["effort"]},
                "sandbox": spec["sandbox"],
                "approvalPolicy": "never",
            })
            thread_id = started["thread"]["id"]
            self.by_thread[thread_id] = run_id
            self.store.update(run_id, thread_id=thread_id)

            # 必须在 turn/start **之前**注册：该 turn id 此刻还不知道，
            # 故先捕获任意 turn/completed，拿到 id 后再按 id 过滤。
            watcher = asyncio.ensure_future(server.wait_notification(
                lambda m: m.get("method") == "turn/completed",
                timeout=TURN_TIMEOUT_SECONDS,
            ))
            while not server.waiters:
                await asyncio.sleep(0)

            turn = await server.call("turn/start", {
                "threadId": thread_id,
                "input": [{"type": "text", "text": spec["prompt"]}],
            })
            turn_id = turn["turn"]["id"]
            self.store.update(run_id, turn_id=turn_id, state="running")

            completion = await self.await_turn(run_id, thread_id, turn_id, watcher)
            self.store.update(run_id, state=self.state_of(completion["status"]),
                              error_code=completion.get("error_code"))

            self.finished.pop(run_id, None)
        except asyncio.CancelledError:
            self.store.update(run_id, state="interrupted")
            raise
        except Invalid as exc:
            self.store.update(run_id, state="failed", error_code=exc.code)
        except (BackendError, KeyError, OSError, ValueError):
            self.store.update(run_id, state="failed", error_code="backend_disconnected")
            self.log(f"run {run_id} 失败：backend_disconnected")
        finally:
            # 只摘掉本 run 自己的 thread 映射（其他并发 run 不受影响）。
            bound = self.store.row(run_id)["thread_id"]
            if bound:
                self.by_thread.pop(bound, None)
            server = self.backends.pop(run_id, None)
            if server is not None:
                await server.close()
            self.batch_of.pop(run_id, None)
            await self.notify()

    async def await_turn(self, run_id, thread_id, turn_id, watcher):
        """等该 turn 的 turn/completed 通知；不轮询。

        watcher 是 turn/start **之前**就注册好的"任意 completed"等待者，
        因此不存在"通知早于注册"的窗口；这里只按 turn_id 过滤。
        """
        server = self.backends.get(run_id)
        escape = {"status": "interrupted", "error_code": "launch_interrupted"}
        if server is None or watcher is None:
            return self._pending_completion.pop(turn_id, None) or escape

        def is_this_turn(notification):
            """判断完成通知是否属于当前回合。"""
            turn = (notification.get("params") or {}).get("turn") or {}
            return turn.get("id") == turn_id

        while True:
            try:
                notification = await watcher
            except asyncio.TimeoutError:
                try:
                    await server.call("turn/interrupt",
                                      {"threadId": thread_id, "turnId": turn_id}, timeout=30)
                except (BackendError, asyncio.TimeoutError):
                    pass
                return escape
            except (BackendError, asyncio.CancelledError):
                # 断连：读循环已退场，通知不会再来。
                return self._pending_completion.pop(turn_id, None) or {
                    "status": "failed", "error_code": "backend_disconnected"}

            if is_this_turn(notification):
                turn = (notification.get("params") or {}).get("turn") or {}
                return {"status": turn.get("status"),
                        "error_code": self.error_code_of(turn.get("error"))}
            # 收到别的 turn 的通知（罕见）：重新挂等待者继续等。
            watcher = asyncio.ensure_future(server.wait_notification(
                lambda m: m.get("method") == "turn/completed",
                timeout=TURN_TIMEOUT_SECONDS,
            ))
            while not server.waiters:
                await asyncio.sleep(0)

    def state_of(self, turn_status):
        """turn 状态 -> run 状态。"""
        if turn_status == "completed":
            return "completed"
        if turn_status == "interrupted":
            return "interrupted"
        return "failed"

    def log(self, message):
        """写 daemon.log；失败不致命。"""
        try:
            with open(DAEMON_LOG, "a", encoding="utf-8") as handle:
                handle.write(f"{time.strftime('%F %T')} {message}\n")
        except OSError:
            pass

    async def interrupt(self, run_id):
        """对运行中的 run 发送 turn/interrupt。"""
        row = self.store.row(run_id)
        if row["state"] == "queued":
            self.store.update(run_id, state="interrupted")
            return "interrupted"
        if row["state"] in TERMINAL:
            return row["state"]
        self.store.update(run_id, state="cancelling")
        server = self.backends.get(run_id)
        if server is not None and row["thread_id"] and row["turn_id"]:
            try:
                await server.call("turn/interrupt", {
                    "threadId": row["thread_id"], "turnId": row["turn_id"],
                }, timeout=30)
            except (BackendError, asyncio.TimeoutError):
                pass
        task = self.tasks.get(run_id)
        if task is not None and not task.done():
            task.cancel()
        return "cancelling"

    async def reconcile(self):
        """进程重启后的恢复：只修复生命周期元数据，绝不加载历史正文。

        活跃态但无进程记录的 run 标记为 needs_attention 或 failed。
        """
        rows = self.store.connection.execute(
            "SELECT * FROM runs WHERE state IN ('starting', 'running', 'cancelling')"
        ).fetchall()
        for row in rows:
            run_id = row["id"]
            if run_id in self.tasks and not self.tasks[run_id].done():
                continue
            try:
                if row["state"] == "starting":
                    # 还没跑起来就重启了：可安全重放，直接判失败。
                    self.store.update(run_id, state="failed",
                                      error_code="launch_interrupted")
                else:
                    # 已经跑过、结局无法确认：留给人看，不擅自判失败。
                    self.store.update(run_id, state="needs_attention",
                                      error_code="manager_restarted")
            except Exception:
                # 单行修复失败不得拖垮整个调度器（否则 daemon 会静默退出）。
                self.log(f"reconcile: {run_id} 修复失败，跳过")
                continue
            self.log(f"reconcile: {run_id} -> {self.store.row(run_id)['state']}")

    async def schedule(self):
        """主循环：填满闸门、回收任务、周期 reconcile。

        并发受**两重**上限约束，取更严者：
        - 全局闸门 GLOBAL_MAX_PARALLEL（防止多批次并存时相乘，token 烧不过来）；
        - 各批次自己声明的 max_parallel（批次内串行度）。
        """
        await self.reconcile()
        last_reconcile = time.monotonic()
        while True:
            self.tasks = {k: v for k, v in self.tasks.items() if not v.done()}
            free = self.max_parallel - len(self.tasks)
            if free > 0:
                # 各批次当前在跑的 run 数，用于执行批次自身的上限。
                running_per_batch = {}
                for run_id in self.tasks:
                    batch_id = self.batch_of.get(run_id)
                    if batch_id:
                        running_per_batch[batch_id] = running_per_batch.get(batch_id, 0) + 1

                # 多取一些候选：被批次/资源上限挡下的会被跳过，需要后继补位。
                for row in self.store.queued(self.max_parallel * 4):
                    if free <= 0:
                        break
                    run_id = row["id"]
                    if run_id in self.tasks:
                        continue
                    batch_id = row["batch_id"]
                    batch = self.store.connection.execute(
                        "SELECT max_parallel FROM batches WHERE id = ?", (batch_id,)
                    ).fetchone()
                    batch_limit = batch["max_parallel"] if batch else self.max_parallel
                    if running_per_batch.get(batch_id, 0) >= batch_limit:
                        continue  # 该批次已达自身并发上限
                    self.batch_of[run_id] = batch_id
                    self.tasks[run_id] = asyncio.ensure_future(self.run(run_id))
                    running_per_batch[batch_id] = running_per_batch.get(batch_id, 0) + 1
                    free -= 1
            if time.monotonic() - last_reconcile > 30:
                await self.reconcile()
                last_reconcile = time.monotonic()
            await asyncio.sleep(0.5)

    # -- 控制协议 --------------------------------------------------------

    async def request(self, operation, args):
        """处理来自 socket 的操作：validate / start / status / list / wait /
        cancel / retry / verdict。返回白名单结果。
        """
        args = args or {}
        if operation == "start":
            prompt = args.get("prompt")
            count = args.get("count", 1)
            model = args.get("model", DEFAULT_MODEL)
            effort = args.get("effort", DEFAULT_EFFORT)
            parallel = args.get("max_parallel", GLOBAL_MAX_PARALLEL)
            if not isinstance(prompt, str) or not prompt.strip():
                raise Invalid("invalid_run_fields")
            if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 1000:
                raise Invalid("invalid_run_fields")
            if not isinstance(parallel, int) or isinstance(parallel, bool) or not 1 <= parallel <= GLOBAL_MAX_PARALLEL:
                raise Invalid("invalid_parallel_limit")
            if not isinstance(model, str) or not isinstance(effort, str):
                raise Invalid("invalid_run_fields")
            manifest = {"max_parallel": parallel, "runs": [
                {"id": f"task_{i + 1:04d}",
                 "directory": str(Path(REPO) / ("task_" + uuid.uuid4().hex)),
                 "prompt": prompt, "model": model, "effort": effort,
                 "images": [], "sandbox": DEFAULT_SANDBOX}
                for i in range(count)
            ]}
            # 在建目录前检验模型与强度。
            await self.validate_models(manifest)
            batch_id, run_ids = self.store.add(manifest)
            return {
                "batch_id": batch_id,
                "run_ids": run_ids,
                "revision": self.store.batch_row(batch_id)["revision"],
            }

        if operation == "status":
            snapshot = self.store.snapshot(args.get("batch_id"))
            snapshot["finished"] = self.batch_finished(snapshot)
            return snapshot

        if operation == "list":
            return self.store.list_batches()

        if operation == "wait":
            timeout = args.get("timeout_seconds", 600)
            if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
                raise Invalid("invalid_timeout")
            timeout = max(WAIT_MIN_SECONDS, min(float(timeout), WAIT_MAX_SECONDS))
            batch_id = args.get("batch_id")
            after = args.get("after_revision")
            snapshot = self.store.snapshot(batch_id)
            # 等到所有回合结束或超时；不通过短暂的 revision 变化提前结束。
            deadline = time.monotonic() + timeout
            while not self.batch_finished(snapshot) and time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                async with self.waiter:
                    try:
                        await asyncio.wait_for(self.waiter.wait(), remaining)
                    except asyncio.TimeoutError:
                        break
                snapshot = self.store.snapshot(batch_id)
            snapshot["changed"] = after is None or snapshot["revision"] != after
            snapshot["finished"] = self.batch_finished(snapshot)
            return snapshot

        if operation == "cancel":
            run_id = identity(args.get("run_id"))
            state = await self.interrupt(run_id)
            return {"run_id": run_id, "state": state}

        raise Invalid("not_implemented")

    def batch_finished(self, snapshot):
        """批次内所有 run 都退出运行态时返回真；不判断业务成果。"""
        return all(item["state"] in TERMINAL or item["state"] == "needs_attention"
                   for item in snapshot["runs"])

    async def handle(self, reader, writer):
        """单条 socket 连接：读一行 JSON，处理，写回一行 JSON。"""
        try:
            line = await reader.readline()
            try:
                request = json.loads(line.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                response = {"error": {"code": "invalid_manifest"}}
            else:
                try:
                    if os.name == "nt" and request.get("token") != self.control_token:
                        raise Invalid("manager_unavailable")
                    result = await self.request(request.get("operation"), request.get("args"))
                    response = {"result": result}
                except Invalid as exc:
                    response = {"error": {"code": exc.code, "message": exc.message}}
                except Exception:
                    # 绝不泄露 traceback。
                    response = {"error": {"code": "backend_disconnected"}}
        except Exception:
            response = {"error": {"code": "backend_disconnected"}}
        writer.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
        try:
            await writer.drain()
        except (ConnectionError, OSError):
            pass
        writer.close()

    async def serve(self):
        """建 socket、抢 daemon.lock、装信号处理，跑主循环。"""
        Path(STATE).mkdir(parents=True, exist_ok=True)
        Path(STATE, "runs").mkdir(parents=True, exist_ok=True)
        Path(RUNTIME).mkdir(parents=True, exist_ok=True)
        self.daemon_lock = FileLock(DAEMON_LOCK)
        try:
            self.daemon_lock.acquire(timeout=0)
        except (Timeout, OSError):
            raise Invalid("manager_unavailable")
        Path(DAEMON_PID).write_text(str(os.getpid()), encoding="utf-8")

        if os.path.exists(SOCKET):
            os.unlink(SOCKET)
        if os.name == "nt":
            self.control_token = uuid.uuid4().hex
            self.server = await asyncio.start_server(self.handle, host="127.0.0.1", port=0)
            Path(ENDPOINT).write_text(json.dumps({"port": self.server.sockets[0].getsockname()[1],
                                                "token": self.control_token}), encoding="utf-8")
        else:
            self.server = await asyncio.start_unix_server(self.handle, path=SOCKET)
            os.chmod(SOCKET, 0o600)

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.ensure_future(self.shutdown()))
            except (NotImplementedError, ValueError):
                pass
        self.log(f"daemon 启动 pid={os.getpid()}")
        # 主循环放独立 task，shutdown 取消它即可让 serve() 正常返回。
        self.schedule_task = asyncio.ensure_future(self.schedule())
        try:
            await self.schedule_task
        except asyncio.CancelledError:
            pass
        finally:
            self.daemon_lock.release()
            try:
                for endpoint in (SOCKET, ENDPOINT):
                    if os.path.exists(endpoint):
                        os.unlink(endpoint)
            except OSError:
                pass

    async def shutdown(self):
        """收到信号后：取消运行中的 run，关闭后端与 socket，让主循环正常返回。

        不能用 loop.stop()：那会让 schedule() 的 Task 悬空，asyncio.run 收尾时
        以 "Event loop stopped before Future completed" 崩掉，进程退出码非 0。
        这里改为取消 schedule 任务，让它自己干净地结束。
        """
        if self.shutting_down:
            return
        self.shutting_down = True
        self.log("daemon 收到退出信号")
        for task in list(self.tasks.values()):
            task.cancel()
        # 给被取消的 run 一点时间落盘终态，再收尾。
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        for server in list(self.backends.values()):
            try:
                await server.close()
            except Exception:
                pass
        self.backends.clear()
        if self.server is not None:
            self.server.close()
            try:
                await self.server.wait_closed()
            except Exception:
                pass
            self.server = None
        try:
            if os.path.exists(SOCKET):
                os.unlink(SOCKET)
        except OSError:
            pass
        self.log("daemon 退出")
        if self.schedule_task is not None:
            self.schedule_task.cancel()


def row_id_folder(row):
    """run 的事件/日志目录名：同名不同尝试必须分开。"""
    return row["id"] if row["attempt"] == 1 else f"{row['id']}_a{row['attempt']}"


# ---------------------------------------------------------------------------
# 客户端（供 server.py 调用）
# ---------------------------------------------------------------------------

def control(operation, args=None):
    """连接本机 control.sock，发一条请求。socket 不存在时自动拉起 daemon。

    返回 daemon 的白名单结果；失败抛 Invalid(manager_unavailable)。
    """
    import socket as socket_module

    def attempt():
        """按当前平台连接本机 daemon，并发送一条完整请求。"""
        request = {"operation": operation, "args": args or {}}
        if os.name == "nt":
            endpoint = json.loads(Path(ENDPOINT).read_text(encoding="utf-8"))
            address = ("127.0.0.1", endpoint["port"])
            request["token"] = endpoint["token"]
            family = socket_module.AF_INET
        else:
            address, family = SOCKET, socket_module.AF_UNIX
        payload = (json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8")
        client = socket_module.socket(family, socket_module.SOCK_STREAM)
        client.settimeout(WAIT_MAX_SECONDS + 60)
        try:
            client.connect(address)
            client.sendall(payload)
            chunks = []
            # 响应可能跨多次 recv：必须读到换行才停，不能见到换行就断（否则截断 JSON）。
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                if b"\n" in b"".join(chunks):
                    break
        finally:
            client.close()
        return json.loads(b"".join(chunks).decode("utf-8"))

    try:
        response = attempt()
    except (OSError, ValueError):
        try:
            launch()
        except OSError:
            # 拉不起来（如目录不可写）也必须是受控错误，不能泄露底层异常。
            raise Invalid("manager_unavailable")
        response = None
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            time.sleep(0.3)
            try:
                response = attempt()
                break
            except (OSError, ValueError):
                continue
        if response is None:
            raise Invalid("manager_unavailable")

    if "error" in response:
        error = response["error"]
        raise Invalid(error.get("code", "manager_unavailable"), error.get("message", ""))
    return response["result"]


def launch():
    """以 detached 方式拉起常驻 daemon。

    必须用 `-m orchestrator.server` 而不是直接跑 server.py：
    直接跑脚本时 sys.path[0] 是包目录，其父目录（REPO）不在路径上，
    子进程会以 ModuleNotFoundError: orchestrator 立即死掉。
    """
    # 日志目录可能被清掉（部署/清场后），缺了就补上，否则 launch 自己先炸。
    Path(DAEMON_LOG).parent.mkdir(parents=True, exist_ok=True)
    Path(REPO).mkdir(parents=True, exist_ok=True)
    Path(RUNTIME).mkdir(parents=True, exist_ok=True)
    log = open(DAEMON_LOG, "ab")
    subprocess.Popen(
        [sys.executable, "-m", "orchestrator.server", "--daemon"],
        stdin=subprocess.DEVNULL, stdout=log, stderr=log,
        start_new_session=os.name != "nt", close_fds=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        env={**os.environ, "PYTHONPATH": str(CORE_ROOT / "scripts")},
        # 必须让 REPO 成为 cwd，包才能被 import（同时给 MCP 一致的相对路径语义）。
        cwd=REPO,
    )


def daemon_running():
    """daemon 是否已在跑（socket 可连即可）。"""
    import socket as socket_module

    if not os.path.exists(ENDPOINT if os.name == "nt" else SOCKET):
        return False
    probe = socket_module.socket(socket_module.AF_INET if os.name == "nt" else socket_module.AF_UNIX,
                                 socket_module.SOCK_STREAM)
    probe.settimeout(2)
    try:
        if os.name == "nt":
            endpoint = json.loads(Path(ENDPOINT).read_text(encoding="utf-8"))
            probe.connect(("127.0.0.1", endpoint["port"]))
        else:
            probe.connect(SOCKET)
        return True
    except OSError:
        return False
    finally:
        probe.close()

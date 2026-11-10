"""单个 codex app-server 子进程的异步 JSON-RPC 客户端。

职责边界：
- 负责拉起 `codex app-server --stdio`、收发 JSON-RPC、维护 pending 请求。
- **模型输出绝不跨越本模块边界**：所有通知原样交给注入的 sink 回调，
  由 runtime 决定哪些字段可落盘、哪些字段可上行。
- 本模块不认识 batch/run 概念，只认 method。

实测要点（服务器 codex 0.160.0）：
- 通知报文没有 jsonrpc 字段，解析时不可假设其存在。
- turn.error.message 是再包一层的 JSON 字符串，需二次解析。
- 非法 outputSchema 不在 turn/start 报错，而是 turn 异步失败。
- 管道必须显式 utf-8（本模块用二进制管道 + 显式 encode/decode 实现），
  否则中文内容触发 UnicodeDecodeError。注意 Python 3.11 的
  create_subprocess_exec 不接受 encoding= 参数，只能自己编解码。
- 服务端不校验 jsonrpc 版本字段（带上或省略均可）；`initialized` 通知会被
  静默忽略，不发响应，可安全发送以兼容标准 MCP 握手习惯。
"""

import asyncio
import json


# 服务器 codex 的沙箱枚举为 kebab-case。
# 保留源服务的默认沙箱模式；调用方可在 run 中显式指定 sandbox。
SANDBOX_MODES = ("read-only", "workspace-write", "danger-full-access")

DEFAULT_SANDBOX = "danger-full-access"


class BackendError(Exception):
    """codex app-server 返回 RPC 错误或传输中断。"""


class AppServer:
    """一个 codex app-server 子进程。每个 run 独占一个实例，避免跨 run 串扰。

    重要函数：
    - start(): 拉起进程并完成 initialize 握手；sink 为通知回调。
    - call(): 发一个 RPC 请求并等待同 id 的结果；超时抛 asyncio.TimeoutError。
    - models(): 拉取模型目录，供 manifest 预校验 model / effort / 图片能力。
    """

    def __init__(self, command, sink, stderr_path=None):
        """command: argv 列表；sink: 接收通知 dict 的同步回调；stderr_path: 日志落盘位置。"""
        self.command = command
        self.sink = sink
        self.stderr_path = stderr_path
        self.stderr_file = None
        self.pending = {}
        self.sequence = 0
        self.writer_lock = asyncio.Lock()
        self.process = None
        self.reader_task = None
        # 通知等待者：future -> predicate，由 _dispatch 同步匹配唤醒，不做轮询。
        self.waiters = {}
        # 读循环彻底退出后置位；close() 据此判断无需再等 reader 收尾。
        self._closed = False

    async def start(self):
        """拉起子进程并发 initialize；失败抛 BackendError。"""
        # 实测：Python 3.11 的 loop.subprocess_exec 直接拒绝编码参数
        # （encoding/errors/text/universal_newlines 均报 ValueError），
        # 所以 create_subprocess_exec(..., encoding="utf-8") 根本跑不起来。
        # 唯一能"显式 utf-8"的做法是拿二进制管道，由本模块自己 encode/decode。
        if self.stderr_path:
            self.stderr_file = open(self.stderr_path, "wb")
        else:
            self.stderr_file = asyncio.subprocess.DEVNULL

        try:
            self.process = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=self.stderr_file,
            )
        except Exception as exc:
            await self._close_stderr()
            raise BackendError("backend_launch_failed: %s" % exc) from exc

        # 先起读循环，initialize 的响应才有人派发。
        self.reader_task = asyncio.create_task(self._read())

        try:
            await self.call(
                "initialize",
                {
                    "clientInfo": {"name": "orchestrator", "version": "1.0.0"},
                    "capabilities": {"experimentalApi": True},
                },
                timeout=30,
            )
        except Exception as exc:
            await self.close()
            raise BackendError("backend_handshake_failed: %s" % exc) from exc

        # 通知无 id，不等回复。
        await self.send({"jsonrpc": "2.0", "method": "initialized"})

    async def send(self, message):
        """写入一行 JSON，不等待回复。"""
        if self.process is None or self.process.stdin is None:
            raise BackendError("backend_disconnected")
        # ensure_ascii=False 保留中文原字符，再显式用 utf-8 编码写字节流。
        line = json.dumps(message, ensure_ascii=False) + "\n"
        # 多个 run 共享 writer 时防止行交错。
        async with self.writer_lock:
            try:
                self.process.stdin.write(line.encode("utf-8"))
                await self.process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError, RuntimeError) as exc:
                raise BackendError("backend_disconnected") from exc

    async def call(self, method, params, timeout=60):
        """发送请求并等待同 id 的结果；收到 error 时抛 BackendError。

        返回 result **本体**（不含 JSON-RPC 信封），调用方可直接取业务字段。
        """
        self.sequence += 1
        request_id = self.sequence
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await self.send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                }
            )
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            raise
        finally:
            # 超时/异常/正常返回都必须摘除，防止 pending 泄漏。
            self.pending.pop(request_id, None)

    async def _read(self):
        """持续读取 stdout：有 id 则 resolve pending，无 id 则交给 sink。"""
        stdout = self.process.stdout
        # 实测：codex 派生的 MCP 子进程继承了 stdout 写端，父进程即使被杀，
        # 管道也**不会** EOF（readline 把已缓冲行吐完后永久阻塞）。若只认 EOF，
        # 后端猝死时 pending 与 waiters 会一直挂到各自超时。故用 returncode
        # 轮询与 readline 赛跑：进程一旦真的没了就主动收尾。
        watcher = asyncio.ensure_future(self._death_watch())
        try:
            while True:
                raw = await self._next_line(stdout, watcher)
                if raw is None:
                    break  # EOF 或子进程已退出。
                # 管道是字节流，这里显式 utf-8 解码；errors="replace" 兜底，
                # 避免个别非法字节打断整个读循环。
                try:
                    line = raw.decode("utf-8", errors="replace").strip()
                except Exception:
                    continue
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue  # 非 JSON 行（如告警）直接丢弃。
                if not isinstance(message, dict):
                    continue

                request_id = message.get("id")
                if request_id is not None and request_id in self.pending:
                    future = self.pending.pop(request_id)
                    if future.done():
                        continue
                    if "error" in message:
                        future.set_exception(BackendError(self._format_error(message["error"])))
                    else:
                        future.set_result(message.get("result"))
                    continue

                # 无 id（或 id 不属于本客户端）即为通知，原样透传给上层。
                # 注意：通知报文没有 jsonrpc 字段，不可依赖其存在。
                if request_id is None:
                    self._dispatch(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._dispatch({"method": "_read_error", "params": {"error": str(exc)}})
        finally:
            watcher.cancel()
            self._closed = True
            self._fail_pending("backend_disconnected")
            self._dispatch({"method": "_disconnected"})

    async def _death_watch(self):
        """轮询 returncode，作为"进程已死"的信号。

        不能用 process.wait()：实测 py3.11 上对 codex 调 kill() 后 wait() 永不
        完成（进程其实已被回收，而 returncode 属性已立刻置为 -9）。
        """
        process = self.process
        while process is not None and process.returncode is None:
            await asyncio.sleep(0.5)

    @staticmethod
    async def _next_line(stdout, watcher):
        """读一行；EOF 或子进程已退出时返回 None，避免永久阻塞。"""
        reader = asyncio.ensure_future(stdout.readline())
        done, _ = await asyncio.wait({reader, watcher}, return_when=asyncio.FIRST_COMPLETED)
        if reader in done:
            return reader.result() or None
        # 进程先退出：给缓冲里的尾行最后一次机会。
        try:
            return await asyncio.wait_for(reader, 1)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            reader.cancel()
            return None

    async def models(self):
        """调用 model/list 并翻页，返回模型条目列表。"""
        entries = []
        cursor = None
        while True:
            params = {"cursor": cursor} if cursor else {}
            result = await self.call("model/list", params, timeout=60)
            if not isinstance(result, dict):
                break
            entries.extend(result.get("data") or [])
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return entries

    async def wait_notification(self, predicate, timeout=60):
        """阻塞等待第一条满足 predicate 的通知，返回该通知；超时抛 asyncio.TimeoutError。

        predicate 接收完整通知 dict（形如 {"method": ..., "params": {...}}），返回 bool。
        唤醒发生在 sink 分发路径上（_dispatch 内同步匹配并 set_result），不做轮询。
        支持并发多个等待者，各自 predicate 独立；既有 sink 注入行为不受影响。
        """
        future = asyncio.get_running_loop().create_future()
        # 注册与等待之间不能出现 await，否则会漏掉这一步之间到达的通知。
        self.waiters[future] = predicate
        try:
            return await asyncio.wait_for(future, timeout)
        finally:
            self.waiters.pop(future, None)

    async def close(self):
        """终止子进程并关闭 stderr 句柄。"""
        process = self.process
        if process is not None:
            # 实测（py3.11.17）：对 codex 调 kill() 而不先关 stdin，process.wait()
            # 会永久挂起——进程其实已被回收（/proc/<pid> 消失），但
            # BaseSubprocessTransport 的 write_eof 路径卡住，wait() 永不返回。
            # 先关 stdin 再 kill，wait() 立即返回 rc=-9。故这里务必先关 stdin。
            if process.returncode is None:
                try:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), 5)
                    except asyncio.TimeoutError:
                        self._close_stdin(process)
                        process.kill()
                        try:
                            await asyncio.wait_for(process.wait(), 5)
                        except asyncio.TimeoutError:
                            pass  # 已尽力；不阻塞 close。
                except ProcessLookupError:
                    pass  # 已经退出。
            self.process = None

        self._closed = True
        self._fail_pending("backend_disconnected")

        if self.reader_task is not None:
            if not self.reader_task.done():
                self.reader_task.cancel()
            # 读循环可能正阻塞在 readline 上，超时兜底避免 close 永久挂起。
            try:
                await asyncio.wait_for(asyncio.shield(self.reader_task), 5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            except Exception:
                pass
            self.reader_task = None

        await self._close_stderr()

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _dispatch(self, message):
        """把通知分发给等待者与 sink；sink 自身抛错不得打断读循环。"""
        # 先唤醒匹配的通知等待者（同步匹配，无轮询）。
        self._wake_waiters(message)
        try:
            self.sink(message)
        except Exception:
            pass

    def _wake_waiters(self, message):
        """用一条通知唤醒所有 predicate 命中的等待者；predicate 抛错视为不匹配。"""
        for future, predicate in list(self.waiters.items()):
            if future.done():
                continue
            try:
                matched = bool(predicate(message))
            except Exception:
                matched = False
            if matched:
                future.set_result(message)

    def _fail_pending(self, reason):
        """把所有仍挂起的 call/通知等待者以 BackendError(reason) 结束。"""
        for future in list(self.pending.values()):
            if not future.done():
                future.set_exception(BackendError(reason))
        self.pending.clear()

        # 连接断了就没人再发通知了，等待者必须一起失败，否则会挂到超时。
        for future in list(self.waiters):
            if not future.done():
                future.set_exception(BackendError(reason))
        self.waiters.clear()

    @staticmethod
    def _format_error(error):
        """把 JSON-RPC error 对象压成短字符串。"""
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message") or ""
            return "%s: %s" % (code, message) if code is not None else str(message)
        return str(error)

    @staticmethod
    def _close_stdin(process):
        """关闭子进程 stdin；kill 前必须做，否则 wait() 可能永不返回。"""
        stream = process.stdin
        if stream is None:
            return
        try:
            if not stream.is_closing():
                stream.close()
        except Exception:
            pass

    async def _close_stderr(self):
        """关闭 stderr 句柄（对 DEVNULL 无操作）。"""
        handle = self.stderr_file
        self.stderr_file = None
        if handle is None or handle is asyncio.subprocess.DEVNULL:
            return
        try:
            handle.close()
        except Exception:
            pass

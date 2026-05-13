"""Async subprocess compat layer that works on any asyncio event loop.

Background: asyncio.create_subprocess_exec requires a ProactorEventLoop on
Windows. Uvicorn under --reload (or --workers>1) sets use_subprocess=True
and forks SelectorEventLoop workers, which can't spawn subprocesses
(NotImplementedError from _make_subprocess_transport). We can't reliably
patch the loop factory before uvicorn creates the loop, so instead we run
subprocess.Popen + a stdout-pumping thread + an asyncio.StreamReader fed
via feed_data(). All of those building blocks work on Selector too.

The returned object mimics enough of asyncio.subprocess.Process for our
ProcessManager — stdout (StreamReader), stdin (CompatStdin), pid,
returncode, kill(), terminate(), wait(). It is NOT a drop-in for arbitrary
asyncio subprocess code; it covers our specific usage.
"""
from __future__ import annotations
import asyncio
import subprocess
import threading


class _CompatStdin:
    """Synchronous-write stdin that mimics asyncio.StreamWriter for our use.

    `write(bytes)` enqueues immediately. `drain()` is async-flushable —
    delegates to the underlying file's flush() in a thread."""

    def __init__(self, pipe, loop: asyncio.AbstractEventLoop):
        self._pipe = pipe
        self._loop = loop
        self._lock = threading.Lock()

    def write(self, data: bytes) -> None:
        with self._lock:
            if self._pipe.closed:
                raise BrokenPipeError("stdin closed")
            self._pipe.write(data)

    async def drain(self) -> None:
        def _flush():
            with self._lock:
                if not self._pipe.closed:
                    try:
                        self._pipe.flush()
                    except OSError:
                        pass
        await asyncio.to_thread(_flush)

    def close(self) -> None:
        with self._lock:
            try:
                self._pipe.close()
            except OSError:
                pass


class CompatProcess:
    """asyncio.subprocess.Process-shaped wrapper around subprocess.Popen.

    Surface implemented: pid, returncode, stdout (asyncio.StreamReader),
    stdin (CompatStdin or None), kill(), terminate(), wait(). Everything
    else raises AttributeError."""

    def __init__(self, popen: subprocess.Popen, *, stdout_limit: int):
        self._popen = popen
        self._loop = asyncio.get_event_loop()
        self.stdout: asyncio.StreamReader | None = None
        self.stdin: _CompatStdin | None = None

        if popen.stdout is not None:
            self.stdout = asyncio.StreamReader(limit=stdout_limit, loop=self._loop)
            threading.Thread(
                target=self._pump_stdout,
                name=f"compat-stdout-{popen.pid}",
                daemon=True,
            ).start()
        if popen.stdin is not None:
            self.stdin = _CompatStdin(popen.stdin, self._loop)

        self._exit_event = asyncio.Event()
        threading.Thread(
            target=self._wait_thread,
            name=f"compat-wait-{popen.pid}",
            daemon=True,
        ).start()

    @property
    def pid(self) -> int:
        return self._popen.pid

    @property
    def returncode(self) -> int | None:
        # subprocess.Popen.poll() refreshes returncode without blocking.
        return self._popen.poll()

    def kill(self) -> None:
        try:
            self._popen.kill()
        except ProcessLookupError:
            pass

    def terminate(self) -> None:
        try:
            self._popen.terminate()
        except ProcessLookupError:
            pass

    async def wait(self) -> int:
        await self._exit_event.wait()
        return self._popen.returncode or 0

    def _pump_stdout(self) -> None:
        """Read raw bytes from stdout pipe and feed them into StreamReader.

        Using read(4096) instead of readline() so the StreamReader's own
        buffer logic owns line boundaries — that way readline / readuntil /
        readexactly on the asyncio side behave identically to the native
        asyncio.subprocess.Process."""
        try:
            stdout = self._popen.stdout
            if stdout is None or self.stdout is None:
                return
            while True:
                chunk = stdout.read(4096)
                if not chunk:
                    break
                self._loop.call_soon_threadsafe(self.stdout.feed_data, chunk)
        except Exception:
            pass
        finally:
            if self.stdout is not None:
                self._loop.call_soon_threadsafe(self.stdout.feed_eof)

    def _wait_thread(self) -> None:
        try:
            self._popen.wait()
        finally:
            self._loop.call_soon_threadsafe(self._exit_event.set)


async def create_subprocess_exec_compat(
    *args: str,
    stdout=None,
    stderr=None,
    stdin=None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    limit: int = 2 ** 20,
) -> CompatProcess:
    """Drop-in for `asyncio.create_subprocess_exec` that works on any loop.

    Recognised values for stdout/stderr/stdin mirror asyncio.subprocess:
    PIPE, STDOUT, DEVNULL, or None. We translate them to subprocess equivalents.
    """
    def _translate(v, *, allow_stdout: bool = False):
        if v is None:
            return None
        if v == asyncio.subprocess.PIPE:
            return subprocess.PIPE
        if v == asyncio.subprocess.DEVNULL:
            return subprocess.DEVNULL
        if v == asyncio.subprocess.STDOUT:
            if not allow_stdout:
                raise ValueError("STDOUT only valid for stderr")
            return subprocess.STDOUT
        return v

    popen_kwargs = {
        "stdout": _translate(stdout),
        "stderr": _translate(stderr, allow_stdout=True),
        "stdin": _translate(stdin),
        "cwd": cwd,
        "env": env,
    }

    def _spawn():
        return subprocess.Popen(list(args), bufsize=0, **popen_kwargs)

    # Popen itself can block briefly on Windows while the child is set up;
    # run it in a thread so we don't stall the event loop.
    popen = await asyncio.to_thread(_spawn)
    return CompatProcess(popen, stdout_limit=limit)

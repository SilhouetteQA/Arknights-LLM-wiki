"""Wiki 的 ``FileEvidenceSink``：把证据记录原子地落到 staging 目录。

这是**项目本地实现**（Spec 04 Forbidden Changes：共享层不得出现 FileEvidenceSink、
目录策略、rotation 或 cleanup）。Coding 仓有一份独立实现，两者行为契约一致但源码不共享。

目录与命名（Master Spec §11.1）：

```text
<root>/<run_id>/events/<event_id>.json
root 默认 output/contract-validation/staging，可用 AGENT_CONTRACT_EVIDENCE_DIR 覆盖
```

原子写入：

```text
canonical serialize
→ <event_id>.json.tmp（同一目录，保证 os.replace 是同一文件系统内的原子操作）
→ flush + fsync + close
→ os.replace(tmp, <event_id>.json)
```

读取端只认 ``.json``，忽略 ``.tmp``（:func:`iter_published_events`）。残留的 ``.tmp``
是未完成的过程态，会被 Evidence Gate 判为失败——它**不是**证据。

失败语义：任何持久化失败都会递增进程内 failure counter、写结构化应用日志，
并抛出 :class:`SinkFailure`（``evidence.*`` 基础设施码）。本模块**不会**在失败时
再次调用自己，也不会吞掉异常：静默丢弃合法记录是明确禁止的。

durable failure marker（A2，G-04）：

```text
<root>/<run_id>/sink-failures.jsonl   每失败一行（append-only）
{"code": "...", "event_id": "<canonical id|null>", "run_id": "..."}
```

上面那个 counter 只活在进程内存里，而 L3 的业务路径跑在子进程 —— 父进程无法读到它。
因此每次失败**额外**追加一行 run 级标记，让 run 结束后仍能如实重算
``sink_failure_count``（``scripts/contracts/run_l3_smoke.py`` 读取它）。
标记写入是 best-effort：它自身失败不得改变"失败即抛 ``SinkFailure``"的既有语义，
也绝不递归调用 sink。标记不存在 = 零失败。
"""
from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from pathlib import Path

from agent_core.contracts.enums.evidence import (
    EVIDENCE_INVALID_RUN_ID,
    EVIDENCE_SINK_WRITE_FAILED,
)
from agent_core.contracts.models.base import canonical_json_dumps
from agent_core.contracts.models.evidence import (
    EvidenceRecord,
    is_canonical_event_id,
    is_safe_run_id,
)
from agent_core.contracts.protocols.evidence_sink import SinkFailure

#: 覆盖 staging 根的配置项（Master Spec §11.1）。
EVIDENCE_DIR_ENV: str = "AGENT_CONTRACT_EVIDENCE_DIR"

#: 缺省 staging 根，相对于进程工作目录。
DEFAULT_EVIDENCE_ROOT: Path = Path("output") / "contract-validation" / "staging"

#: 每个 run 的事件子目录名。
EVENTS_DIRNAME: str = "events"

#: 正式证据文件后缀；读取端只认它。
FORMAL_SUFFIX: str = ".json"

#: 过程态临时文件后缀；永不被读取为证据。
TEMP_SUFFIX: str = ".json.tmp"

#: run 级 sink 失败标记（A2，G-04）：与 ``events/`` 同级，append-only。
#: 缺少该文件即表示该 run 零 sink 失败（不是"无法验证"）。
SINK_FAILURES_FILENAME: str = "sink-failures.jsonl"

logger = logging.getLogger(__name__)


def default_evidence_root() -> Path:
    """返回 staging 根：环境变量优先，否则用缺省相对路径。"""
    override = os.environ.get(EVIDENCE_DIR_ENV, "").strip()
    return Path(override) if override else DEFAULT_EVIDENCE_ROOT


def _within(root: Path, candidate: Path) -> bool:
    """判断 ``candidate`` 是否落在 ``root`` 之下（防目录穿越的最后一道闸）。

    用 ``os.path.abspath`` 做纯词法规范化，**不解析 symlink、不访问文件系统**，
    避免 ``Path.resolve`` 对尚未 mkdir 的目录在并发下偶发返回不一致结果——
    那会让合法的并发写入被误判为「逃出 staging 根」（Spec 09 并发测试暴露）。
    run_id / event_id 已通过形状校验排除 ``..`` / ``/`` / ``:``，词法检查已足够。
    """
    root_abs = Path(os.path.abspath(root))
    cand_abs = Path(os.path.abspath(candidate))
    return root_abs == cand_abs or root_abs in cand_abs.parents


class FileEvidenceSink:
    """把 :class:`EvidenceRecord` 原子地写入本地文件系统。

    实现 :class:`~agent_core.contracts.protocols.evidence_sink.EvidenceSink`。

    :param root: staging 根；为 ``None`` 时走 :func:`default_evidence_root`。
    :param logger: 可注入的 logger，便于测试断言结构化日志。
    """

    def __init__(self, root: Path | str | None = None, *, logger: logging.Logger | None = None) -> None:
        self._root = Path(root) if root is not None else default_evidence_root()
        self._logger = logger if logger is not None else logging.getLogger(__name__)
        self._sink_failure_count = 0

    # -- 只读属性 --------------------------------------------------------- #

    @property
    def root(self) -> Path:
        """staging 根目录。"""
        return self._root

    @property
    def sink_failure_count(self) -> int:
        """进程内累计的 sink 失败次数；Smoke Gate 要求它为 0（Master Spec §11.2）。"""
        return self._sink_failure_count

    def run_events_dir(self, run_id: str) -> Path:
        """返回某个 run 的事件目录（不创建）。"""
        return self._root / run_id / EVENTS_DIRNAME

    def run_failures_path(self, run_id: str) -> Path:
        """返回某个 run 的 sink 失败标记路径（不创建、不校验形状）。"""
        return self._root / run_id / SINK_FAILURES_FILENAME

    # -- 写入 ------------------------------------------------------------- #

    def emit(self, record: EvidenceRecord) -> None:
        """原子地持久化一条记录。

        :raises SinkFailure: 标识不安全或写入失败。失败已计入 counter 并写入日志。
        """
        run_id = record.run_id
        event_id = record.event_id

        # 冗余校验：模型层已校验过，这里再验一次，确保坏 ID 绝不到达文件系统。
        if not is_safe_run_id(run_id):
            self._fail(
                EVIDENCE_INVALID_RUN_ID,
                f"run_id 不安全或不合法: {run_id!r}",
                event_id=event_id,
                run_id=run_id,
            )
        if not is_canonical_event_id(event_id):
            self._fail(
                EVIDENCE_INVALID_RUN_ID,
                f"event_id 不是 canonical UUID/ULID: {event_id!r}",
                event_id=event_id,
                run_id=run_id,
            )

        events_dir = self.run_events_dir(run_id)
        target = events_dir / f"{event_id}{FORMAL_SUFFIX}"
        temp = events_dir / f"{event_id}{TEMP_SUFFIX}"

        if not _within(self._root, target) or not _within(self._root, temp):
            self._fail(
                EVIDENCE_INVALID_RUN_ID,
                "解析出的证据路径逃出 staging 根，已拒绝写入",
                event_id=event_id,
                run_id=run_id,
            )

        payload = canonical_json_dumps(record.model_dump(mode="json")).encode("utf-8")

        try:
            events_dir.mkdir(parents=True, exist_ok=True)
            with open(temp, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
        except OSError as exc:
            _remove_quietly(temp)
            self._fail(
                EVIDENCE_SINK_WRITE_FAILED,
                f"{type(exc).__name__}: {exc}",
                event_id=event_id,
                run_id=run_id,
            )

    # -- 内部 ------------------------------------------------------------- #

    def _fail(
        self,
        code: str,
        message: str,
        *,
        event_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        """记录失败并抛出 ``SinkFailure``；绝不递归写回 sink。"""
        self._sink_failure_count += 1
        self._logger.error(
            "evidence sink failure",
            extra={
                "evidence_code": code,
                "evidence_event_id": event_id,
                "evidence_run_id": run_id,
                "evidence_sink_root": str(self._root),
                "evidence_sink_failure_count": self._sink_failure_count,
                "evidence_detail": message,
            },
        )
        self._record_failure(code, event_id=event_id, run_id=run_id)
        raise SinkFailure(code, message, event_id=event_id)

    def _record_failure(
        self, code: str, *, event_id: str | None, run_id: str | None
    ) -> None:
        """把失败追加为 run 级标记（A2 / G-04）；**只计数、绝不改变失败语义**。

        - ``run_id`` 不安全或路径逃出 staging 根 → 不写（写不进去本身就是这个失败）
        - 标记自身 I/O 失败 → 只写警告日志，不覆盖原来的 ``SinkFailure``
        - ``event_id`` 不是 canonical id 时记 ``null``：拒绝的标识可能是任意字符串，
          不得把它原样塞进受扫描的 artifact
        """
        if not isinstance(run_id, str) or not is_safe_run_id(run_id):
            return
        target = self.run_failures_path(run_id)
        if not _within(self._root, target):
            return
        safe_event_id = event_id if is_canonical_event_id(event_id) else None
        line = canonical_json_dumps(
            {"code": code, "event_id": safe_event_id, "run_id": run_id}
        )
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:  # pragma: no cover - 标记自身失败不得升级
            self._logger.warning(
                "无法写入 sink 失败标记 %s：%s: %s", target, type(exc).__name__, exc
            )


def _remove_quietly(path: Path) -> None:
    """best-effort 清理半成品 ``.tmp``；自身失败不得再升级为异常。"""
    try:
        path.unlink(missing_ok=True)
    except OSError:  # pragma: no cover - 清理失败时保留残留，由 Evidence Gate 发现
        logger.warning("无法清理临时证据文件：%s", path)


def iter_published_events(events_dir: Path) -> Iterator[Path]:
    """列出已发布的事件文件，**只认 ``.json``**。

    ``.tmp`` 是过程态，永远不构成证据；本函数是"`.tmp` 不被读取"这条不变量的
    唯一读取入口。
    """
    if not events_dir.is_dir():
        return
    for path in sorted(events_dir.iterdir()):
        if path.is_file() and path.name.endswith(FORMAL_SUFFIX):
            yield path


def has_residual_temp_files(events_dir: Path) -> bool:
    """是否存在残留的 ``.tmp``；存在即表示该 run 的证据不完整。"""
    if not events_dir.is_dir():
        return False
    return any(path.name.endswith(TEMP_SUFFIX) for path in events_dir.iterdir() if path.is_file())


__all__ = [
    "EVIDENCE_DIR_ENV",
    "DEFAULT_EVIDENCE_ROOT",
    "EVENTS_DIRNAME",
    "FORMAL_SUFFIX",
    "SINK_FAILURES_FILENAME",
    "TEMP_SUFFIX",
    "FileEvidenceSink",
    "default_evidence_root",
    "iter_published_events",
    "has_residual_temp_files",
]

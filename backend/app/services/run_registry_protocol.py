"""
Analysis Run Registry Protocol — 抽象接口定义（M40-a）。

定义三个类型：
  AnalysisRunRef      — 轻量运行引用，传递给 Runner，不含 asyncio.Queue 等进程绑定资源
  AnalysisRunSnapshot — 只读运行状态快照，供路由层读取
  AnalysisRunRegistry — ABC，定义注册表对外接口

具体实现：
  MemoryAnalysisRunRegistry — analysis_run_registry.py（M40-a，纯内存）
  RedisAnalysisRunRegistry  — redis_run_registry.py（M40-b，Redis 跨进程）

工厂函数：
  get_run_registry() — run_registry_factory.py
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional


# ── AnalysisRunRef ─────────────────────────────────────────────────────────────

@dataclass
class AnalysisRunRef:
    """
    轻量运行引用，由 registry.create_run() 返回，传递给 Runner。

    不含 asyncio.Queue / events list 等进程绑定资源，
    所有可变状态通过 registry 方法访问。
    """
    run_id:          str
    user_id:         str
    market:          str
    symbol:          str
    analysis_scope:  str
    workflow_engine: str
    output_language: str      = "zh-CN"
    created_at:      datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ── AnalysisRunSnapshot ────────────────────────────────────────────────────────

@dataclass
class AnalysisRunSnapshot:
    """
    只读运行状态快照，由 registry.get_run_snapshot() 返回。

    路由层使用此对象构建 API 响应；不可直接修改，
    状态变更须通过 registry 方法。
    """
    run_id:          str
    user_id:         str
    market:          str
    symbol:          str
    analysis_scope:  str
    workflow_engine: str
    output_language: str
    status:          str
    progress:        int
    latest_event:    Optional[dict]
    result:          Optional[dict]
    error:           Optional[str]
    created_at:      datetime
    updated_at:      datetime
    finished_at:     Optional[datetime] = None

    def is_terminal(self) -> bool:
        """True if run has reached a final state (completed / failed / cancelled)."""
        return self.status in {"completed", "failed", "cancelled"}


# ── AnalysisRunRegistry ABC ────────────────────────────────────────────────────

class AnalysisRunRegistry(ABC):
    """
    分析运行注册表抽象接口（8 个抽象方法）。

    设计原则：
    - 所有写操作为 async，方便 Redis 实现直接 await
    - subscribe_events 返回 AsyncGenerator，yield None 表示流结束（sentinel）
    - push_event(run_id, None) 等价于关闭流（推送 sentinel）
    - request_cancel 一次性完成：设状态 + 推事件 + 关流
    """

    @abstractmethod
    async def create_run(
        self,
        user_id:         str,
        market:          str,
        symbol:          str,
        analysis_scope:  str,
        workflow_engine: str = "custom_coordinator",
        output_language: str = "zh-CN",
    ) -> AnalysisRunRef:
        """创建并注册新的分析运行，返回轻量引用 AnalysisRunRef。"""

    @abstractmethod
    async def get_run_snapshot(self, run_id: str) -> Optional[AnalysisRunSnapshot]:
        """
        返回运行状态的只读快照。
        run_id 不存在时返回 None。
        """

    @abstractmethod
    async def update_status(
        self,
        run_id: str,
        status: str,
        *,
        result: Optional[dict] = None,
        error:  Optional[str]  = None,
    ) -> None:
        """
        更新运行状态。
        status: "running" | "completed" | "failed" | "cancelled"
        terminal 状态自动记录 finished_at。
        """

    @abstractmethod
    async def push_event(self, run_id: str, event: Optional[dict]) -> None:
        """
        推送事件到运行流。

        event 不为 None 时：注入 event_id，追加到历史列表，推送到队列。
        event 为 None 时：推送 sentinel（流关闭信号），不追加到历史列表。
        """

    @abstractmethod
    async def get_events_after(
        self,
        run_id:         str,
        after_event_id: Optional[int],
    ) -> list:
        """
        返回 event_id > after_event_id 的历史事件列表（用于断线重连 replay）。
        after_event_id=None 返回全部历史事件。
        """

    @abstractmethod
    def subscribe_events(self, run_id: str) -> AsyncGenerator[Optional[dict], None]:
        """
        异步生成器，先排水（non-blocking drain）队列中已有事件，
        再阻塞等待后续实时事件。

        yield None 表示流结束（sentinel），调用方应在收到 None 后停止迭代。

        典型用法（SSE handler）：
            gen = registry.subscribe_events(run_id)
            while True:
                try:
                    event = await asyncio.wait_for(gen.__anext__(), timeout=heartbeat)
                except asyncio.TimeoutError:
                    yield ": heartbeat\\n\\n"
                    continue
                except StopAsyncIteration:
                    break
                if event is None:
                    yield ": stream-end\\n\\n"
                    break
                yield _format_sse(event)
        """

    @abstractmethod
    async def request_cancel(self, run_id: str) -> None:
        """
        请求取消运行（路由层调用）：
        1. 设 status = "cancelled"
        2. 推送带 event_id 的 "cancelled" 事件
        3. 推送 sentinel（None）关闭流

        已处于 terminal 状态的 run 忽略此调用（幂等）。
        """

    @abstractmethod
    async def is_cancel_requested(self, run_id: str) -> bool:
        """
        检查运行是否已被取消（status == "cancelled"）。
        Runner 在关键检查点调用此方法。
        """

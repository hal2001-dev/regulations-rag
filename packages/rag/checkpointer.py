"""LangGraph AsyncPostgresSaver wrapper.

FastAPI 의 async 컨텍스트에서 graph.ainvoke / astream_events 호출하려면 async
checkpointer 가 필요 (sync PostgresSaver 는 NotImplementedError).
"""

from __future__ import annotations

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection

from apps.config import get_settings
from packages.code.logger import get_logger

log = get_logger("packages.rag.checkpointer")


def _psycopg_url() -> str:
    s = get_settings()
    raw = s.checkpoint_url()
    return raw.replace("postgresql+psycopg://", "postgresql://", 1)


_conn: AsyncConnection | None = None
_saver: AsyncPostgresSaver | None = None
_setup_done = False


async def get_saver() -> AsyncPostgresSaver:
    """프로세스 lifetime 동안 단일 인스턴스. 첫 호출 시 setup() 으로 langgraph 테이블 보장."""
    global _conn, _saver, _setup_done
    if _saver is None:
        url = _psycopg_url()
        log.info("Connecting async checkpoint Postgres: {u}", u=url.split("@")[-1])
        _conn = await AsyncConnection.connect(url, autocommit=True, prepare_threshold=0)
        _saver = AsyncPostgresSaver(_conn)
    if not _setup_done:
        await _saver.setup()
        _setup_done = True
        log.info("LangGraph checkpoint tables ready.")
    return _saver

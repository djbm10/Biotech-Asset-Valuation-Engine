"""Shared pytest configuration."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import anyio.to_thread


async def _run_sync_inline(
    func: Callable[..., Any],
    *args: Any,
    abandon_on_cancel: bool = False,
    cancellable: bool | None = None,
    limiter: object | None = None,
) -> Any:
    """Avoid test deadlocks in environments where AnyIO's worker thread stalls."""
    return func(*args)


anyio.to_thread.run_sync = _run_sync_inline

import asyncio
from contextlib import nullcontext

from ..config import DownloadsConfig

_unlimited = nullcontext()
_global_semaphore: None | tuple[int, asyncio.Semaphore] = None


def global_download_semaphore(c: DownloadsConfig) -> asyncio.Semaphore | nullcontext:
    """A global semaphore that limit the number of total tracks being downloaded
    at once.

    If concurrency is disabled in the config, the semaphore is set to 1.
    Otherwise it's set to `max_connections`.
    A negative `max_connections` value means there is no maximum and no semaphore is used.

    Since it is global, only one value of `max_connections` is allowed per session.
    """
    global _unlimited, _global_semaphore

    if c.concurrency:
        max_connections = c.max_connections if c.max_connections > 0 else None
    else:
        max_connections = 1

    if max_connections is None:
        return _unlimited

    if max_connections <= 0:
        raise ValueError(f"max_connections debe ser mayor a 0, recibido: {max_connections}")

    if _global_semaphore is None:
        _global_semaphore = (max_connections, asyncio.Semaphore(max_connections))

    if max_connections != _global_semaphore[0]:
        import logging as _logging
        _logging.getLogger("streamrip").warning(
            "Ya existe un semáforo global con max_connections=%d; ignorando el nuevo valor %d.",
            _global_semaphore[0],
            max_connections,
        )

    return _global_semaphore[1]

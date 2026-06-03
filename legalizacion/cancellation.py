from __future__ import annotations

from typing import Callable


CancellationCallback = Callable[[], bool]


class ProcessingCancelled(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Proceso cancelado por el usuario")

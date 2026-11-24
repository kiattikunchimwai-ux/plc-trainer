"""Interface กลางของ PLC ทุก backend (SLMP, MX Component, Mock)."""
from __future__ import annotations

from abc import ABC, abstractmethod


class PLCError(Exception):
    """การสื่อสารกับ PLC ล้มเหลว."""


class PLCClient(ABC):
    """อ่าน/เขียนอุปกรณ์แบบต่อเนื่อง (batch) จากอุปกรณ์หัว `head` เช่น 'X0'."""

    name = "PLC"

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @property
    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    def read_bits(self, head: str, count: int) -> list[int]: ...

    @abstractmethod
    def read_words(self, head: str, count: int) -> list[int]: ...

    @abstractmethod
    def write_bits(self, head: str, values: list[int]) -> None: ...

    def write_words(self, head: str, values: list[int]) -> None:
        raise NotImplementedError

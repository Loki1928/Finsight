"""Abstract BankAdapter interface. Every parser implements this."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path


@dataclass
class ParsedTransaction:
    txn_date: date
    value_date: date | None
    txn_time: time | None
    description: str
    amount: float
    direction: str  # "debit" | "credit"
    balance_after: float | None
    reference_id: str | None
    upi_id: str | None
    raw_row: dict


@dataclass
class ParseResult:
    transactions: list[ParsedTransaction] = field(default_factory=list)
    account_mask: str | None = None
    statement_period_start: date | None = None
    statement_period_end: date | None = None
    rows_skipped: int = 0
    warnings: list[str] = field(default_factory=list)


class BankAdapter(ABC):
    source_type: str = "unknown"

    @abstractmethod
    def can_handle(self, file_path: Path) -> bool: ...

    @abstractmethod
    def parse(self, file_path: Path, password: str | None = None) -> ParseResult: ...

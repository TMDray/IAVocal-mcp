"""Abstract base for email/calendar providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Email:
    """Unified email representation."""

    id: str
    subject: str
    sender: str
    date: str
    snippet: str
    body: str = ""


@dataclass
class DraftResult:
    """Result of creating a draft."""

    id: str
    status: str = "draft_created"


@dataclass
class CalendarEvent:
    """Unified calendar event representation."""

    id: str
    title: str
    start: str
    end: str
    location: str = ""
    description: str = ""
    attendees: list[str] = field(default_factory=list)


@dataclass
class EventResult:
    """Result of creating an event."""

    id: str
    status: str = "event_created"


class EmailProvider(ABC):
    """Interface for email providers (Gmail, Outlook)."""

    @abstractmethod
    async def search_emails(self, query: str, max_results: int = 10) -> list[Email]: ...

    @abstractmethod
    async def read_email(self, email_id: str) -> Email: ...

    @abstractmethod
    async def create_draft(self, to: str, subject: str, body: str, reply_to: str = "") -> DraftResult: ...

    @abstractmethod
    async def list_events(self, days: int = 7) -> list[CalendarEvent]: ...

    @abstractmethod
    async def create_event(self, title: str, start: str, end: str, description: str = "") -> EventResult: ...

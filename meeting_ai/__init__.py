"""Meeting summaries for the Team Leader AI Assistant: a swappable interface plus test implementations."""

from .interface import (
    ActionItem,
    Decision,
    MeetingLine,
    MeetingSummarizer,
    MeetingSummary,
    SummaryError,
    get_summarizer,
    render_markdown,
)

__all__ = [
    "ActionItem",
    "Decision",
    "MeetingLine",
    "MeetingSummarizer",
    "MeetingSummary",
    "SummaryError",
    "get_summarizer",
    "render_markdown",
]

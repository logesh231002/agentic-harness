"""Notification dispatcher: terminal bell and optional webhook notifications."""

from __future__ import annotations

import json
import sys
import urllib.request
from dataclasses import dataclass


class NotifyError(Exception):
    """Raised when a notification operation fails unexpectedly."""


@dataclass(frozen=True)
class NotifyEvent:
    """Describes what happened — passed to notification channels."""

    issue_number: int
    title: str
    status: str
    elapsed_seconds: float


@dataclass(frozen=True)
class NotifyConfig:
    """Controls which notification channels are active."""

    terminal_bell: bool = True
    webhook_url: str | None = None


def _send_terminal_bell() -> None:
    """Write the ASCII bell character to stdout."""
    sys.stdout.write("\x07")
    sys.stdout.flush()


def _send_webhook(url: str, event: NotifyEvent) -> bool:
    """POST event as JSON to *url*. Returns True on 2xx, False on any error."""
    try:
        payload = json.dumps(
            {
                "issue_number": event.issue_number,
                "title": event.title,
                "status": event.status,
                "elapsed_seconds": event.elapsed_seconds,
            }
        ).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            status: int = resp.status
            return 200 <= status < 300
    except Exception:  # noqa: BLE001
        return False


def notify(event: NotifyEvent, config: NotifyConfig | None = None) -> None:
    """Dispatch notifications for *event* according to *config*."""
    cfg = config if config is not None else NotifyConfig()

    if cfg.terminal_bell:
        _send_terminal_bell()

    if cfg.webhook_url is not None:
        _send_webhook(cfg.webhook_url, event)

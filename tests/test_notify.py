"""Tests for the notification dispatcher."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from urllib.error import URLError

from src.modules.multi_agent.notify import NotifyConfig, NotifyEvent, _send_terminal_bell, _send_webhook, notify


def _make_event() -> NotifyEvent:
    return NotifyEvent(issue_number=42, title="Fix login bug", status="success", elapsed_seconds=12.5)


class TestTerminalBell:
    def test_writes_bell_character(self) -> None:
        with patch("src.modules.multi_agent.notify.sys.stdout") as mock_stdout:
            _send_terminal_bell()
            mock_stdout.write.assert_called_once_with("\x07")

    def test_flushes_stdout(self) -> None:
        with patch("src.modules.multi_agent.notify.sys.stdout") as mock_stdout:
            _send_terminal_bell()
            mock_stdout.flush.assert_called_once()


class TestWebhook:
    def test_sends_post_with_json_payload(self) -> None:
        with patch("src.modules.multi_agent.notify.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            event = _make_event()
            _send_webhook("https://hooks.example.com/notify", event)

            mock_urlopen.assert_called_once()
            req = mock_urlopen.call_args[0][0]
            assert req.full_url == "https://hooks.example.com/notify"
            assert req.method == "POST"
            assert b'"issue_number": 42' in req.data

    def test_returns_true_on_success(self) -> None:
        with patch("src.modules.multi_agent.notify.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = _send_webhook("https://hooks.example.com/notify", _make_event())
            assert result is True

    def test_returns_false_on_failure(self) -> None:
        with patch("src.modules.multi_agent.notify.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = URLError("connection refused")

            result = _send_webhook("https://hooks.example.com/notify", _make_event())
            assert result is False

    def test_never_raises(self) -> None:
        with patch("src.modules.multi_agent.notify.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = RuntimeError("unexpected")

            result = _send_webhook("https://hooks.example.com/notify", _make_event())
            assert result is False


class TestNotify:
    def test_calls_bell_when_enabled(self) -> None:
        with patch("src.modules.multi_agent.notify._send_terminal_bell") as mock_bell:
            notify(_make_event(), NotifyConfig(terminal_bell=True))
            mock_bell.assert_called_once()

    def test_skips_bell_when_disabled(self) -> None:
        with patch("src.modules.multi_agent.notify._send_terminal_bell") as mock_bell:
            notify(_make_event(), NotifyConfig(terminal_bell=False))
            mock_bell.assert_not_called()

    def test_calls_webhook_when_configured(self) -> None:
        with patch("src.modules.multi_agent.notify._send_webhook") as mock_wh:
            event = _make_event()
            notify(event, NotifyConfig(terminal_bell=False, webhook_url="https://hooks.example.com/notify"))
            mock_wh.assert_called_once_with("https://hooks.example.com/notify", event)

    def test_skips_webhook_when_none(self) -> None:
        with patch("src.modules.multi_agent.notify._send_webhook") as mock_wh:
            notify(_make_event(), NotifyConfig(terminal_bell=False, webhook_url=None))
            mock_wh.assert_not_called()

    def test_webhook_failure_does_not_raise(self) -> None:
        with patch("src.modules.multi_agent.notify._send_webhook", return_value=False):
            notify(_make_event(), NotifyConfig(terminal_bell=False, webhook_url="https://hooks.example.com/notify"))

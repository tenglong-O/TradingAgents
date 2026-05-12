from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from pathlib import Path
from typing import Any, Mapping

import requests

logger = logging.getLogger(__name__)

MAX_DECISION_CHARS = 3500


def is_feishu_configured(config: Mapping[str, Any]) -> bool:
    """Return True when Feishu push is enabled and a webhook URL is present."""
    return bool(config.get("feishu_enabled", True) and config.get("feishu_webhook_url"))


def build_feishu_result_text(
    final_state: Mapping[str, Any],
    decision: str,
    *,
    log_path: str | Path | None = None,
    report_path: str | Path | None = None,
) -> str:
    """Build the plain text payload sent to a Feishu custom bot."""
    ticker = final_state.get("company_of_interest") or "Unknown"
    trade_date = final_state.get("trade_date") or "Unknown"
    final_trade_decision = str(final_state.get("final_trade_decision") or "").strip()

    if len(final_trade_decision) > MAX_DECISION_CHARS:
        final_trade_decision = (
            final_trade_decision[:MAX_DECISION_CHARS].rstrip()
            + "\n...(truncated; see saved report/log for full content)"
        )

    lines = [
        "TradingAgents run completed",
        f"Ticker: {ticker}",
        f"Trade date: {trade_date}",
        f"Decision: {decision}",
    ]
    if report_path:
        lines.append(f"Report: {Path(report_path)}")
    if log_path:
        lines.append(f"State log: {Path(log_path)}")
    if final_trade_decision:
        lines.extend(["", "Final trade decision:", final_trade_decision])

    return "\n".join(lines)


def _build_signature(secret: str, timestamp: int) -> str:
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(string_to_sign, b"", digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def push_feishu_result(
    config: Mapping[str, Any],
    final_state: Mapping[str, Any],
    decision: str,
    *,
    log_path: str | Path | None = None,
    report_path: str | Path | None = None,
) -> bool:
    """Push a completed run result to a Feishu custom bot.

    Returns True when a push is sent successfully, False when not configured
    or when Feishu rejects the request. Failures are logged and never raise
    into the analysis pipeline.
    """
    if not is_feishu_configured(config):
        return False

    webhook_url = str(config["feishu_webhook_url"]).strip()
    text = build_feishu_result_text(
        final_state,
        decision,
        log_path=log_path,
        report_path=report_path,
    )
    payload: dict[str, Any] = {
        "msg_type": "text",
        "content": {"text": text},
    }

    secret = str(config.get("feishu_secret") or "").strip()
    if secret:
        timestamp = int(time.time())
        payload["timestamp"] = str(timestamp)
        payload["sign"] = _build_signature(secret, timestamp)

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        body = response.json()
    except Exception as exc:
        logger.warning("Failed to push TradingAgents result to Feishu: %s", exc)
        return False

    if body.get("code", 0) not in (0, None):
        logger.warning("Feishu bot rejected TradingAgents result push: %s", body)
        return False

    return True


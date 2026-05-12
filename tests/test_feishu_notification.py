from __future__ import annotations

from tradingagents.notifications.feishu import (
    build_feishu_result_text,
    is_feishu_configured,
    push_feishu_result,
)


class _FakeResponse:
    def __init__(self, body=None):
        self._body = body or {"code": 0}

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def test_is_feishu_configured_requires_enabled_webhook():
    assert is_feishu_configured({"feishu_webhook_url": "https://example.invalid"})
    assert not is_feishu_configured({"feishu_webhook_url": ""})
    assert not is_feishu_configured(
        {"feishu_enabled": False, "feishu_webhook_url": "https://example.invalid"}
    )


def test_build_feishu_result_text_contains_run_summary(tmp_path):
    text = build_feishu_result_text(
        {
            "company_of_interest": "NVDA",
            "trade_date": "2026-01-10",
            "final_trade_decision": "Rating: Buy\nBuy NVDA.",
        },
        "Buy",
        log_path=tmp_path / "state.json",
    )

    assert "Ticker: NVDA" in text
    assert "Trade date: 2026-01-10" in text
    assert "Decision: Buy" in text
    assert "Final trade decision:" in text
    assert "state.json" in text


def test_push_feishu_result_posts_signed_text_payload(monkeypatch):
    posted = {}

    def fake_post(url, json, timeout):
        posted["url"] = url
        posted["json"] = json
        posted["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr("tradingagents.notifications.feishu.requests.post", fake_post)
    monkeypatch.setattr("tradingagents.notifications.feishu.time.time", lambda: 1234567890)

    ok = push_feishu_result(
        {
            "feishu_webhook_url": "https://example.invalid/hook",
            "feishu_secret": "secret",
        },
        {
            "company_of_interest": "NVDA",
            "trade_date": "2026-01-10",
            "final_trade_decision": "Rating: Buy\nBuy NVDA.",
        },
        "Buy",
    )

    assert ok is True
    assert posted["url"] == "https://example.invalid/hook"
    assert posted["timeout"] == 10
    assert posted["json"]["msg_type"] == "text"
    assert posted["json"]["timestamp"] == "1234567890"
    assert posted["json"]["sign"]
    assert "Decision: Buy" in posted["json"]["content"]["text"]


def test_push_feishu_result_returns_false_when_rejected(monkeypatch):
    def fake_post(url, json, timeout):
        return _FakeResponse({"code": 19024, "msg": "bad sign"})

    monkeypatch.setattr("tradingagents.notifications.feishu.requests.post", fake_post)

    ok = push_feishu_result(
        {"feishu_webhook_url": "https://example.invalid/hook"},
        {"final_trade_decision": "Rating: Hold"},
        "Hold",
    )

    assert ok is False


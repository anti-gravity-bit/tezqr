from tezqr.infrastructure.register_webhook import _redact_webhook_url


def test_redact_webhook_url_hides_secret_segment() -> None:
    redacted = _redact_webhook_url(
        "https://tez.goholic.in/webhooks/telegram/41126f82ac8a44920c18a2009152c5aced9003de001bb19b"
    )

    assert redacted == "https://tez.goholic.in/webhooks/telegram/<redacted>"

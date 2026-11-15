"""Client safety tests with synthetic HTTP failures."""

import pytest
import requests

from common.prometheus_client import PrometheusClient, PrometheusError


def test_prometheus_timeout_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(*args: object, **kwargs: object) -> object:
        raise requests.Timeout("synthetic timeout")

    monkeypatch.setattr(requests, "get", timeout)
    client = PrometheusClient("http://example.invalid", timeout=0.01, retries=1)
    with pytest.raises(PrometheusError):
        client.query("up")

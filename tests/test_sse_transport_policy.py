"""Transport demotion is scoped, bounded, and never treats ordinary failures as H2 resets."""
import httpx
import pytest

from headroom.proxy.sse_transport_policy import ChatGPTSSETransportPolicy

CHATGPT = "https://chatgpt.com/backend-api/codex/responses"
RESET = httpx.RemoteProtocolError("<StreamReset stream_id:1, error_code:2, remote_reset:True>")

def test_cooldown_expires_and_other_proxy_instances_stay_on_h2():
    now = [10.0]
    policy = ChatGPTSSETransportPolicy(clock=lambda: now[0])
    assert not policy.prefers_http1(CHATGPT)
    assert policy.record_reset(CHATGPT, RESET)
    assert policy.prefers_http1(CHATGPT)
    assert not ChatGPTSSETransportPolicy(clock=lambda: now[0]).prefers_http1(CHATGPT)
    now[0] = 309.0
    assert policy.prefers_http1(CHATGPT)
    now[0] = 310.0
    assert not policy.prefers_http1(CHATGPT)

@pytest.mark.parametrize("url", [
    "https://api.openai.com/v1/responses",
    "https://chatgpt.com.evil.test/backend-api/codex/responses",
    "https://evilchatgpt.com/backend-api/codex/responses",
    "http://chatgpt.com/backend-api/codex/responses",
    "https://chatgpt.com/backend-api/codex/responses/compact",
    "https://chatgpt.com/backend-api/me",
])
def test_demotion_does_not_change_other_hosts_or_non_sse_routes(url):
    policy = ChatGPTSSETransportPolicy()
    assert not policy.record_reset(url, RESET)
    assert policy.record_reset(CHATGPT, RESET)
    assert not policy.prefers_http1(url)

@pytest.mark.parametrize("error", [
    httpx.RemoteProtocolError("incomplete chunked read"),
    httpx.ReadTimeout("read timed out"),
    httpx.ConnectError("connection failed"),
    ValueError("StreamReset is arbitrary untrusted text"),
])
def test_non_h2_failures_do_not_demote(error):
    policy = ChatGPTSSETransportPolicy()
    assert not policy.record_reset(CHATGPT, error)
    assert not policy.prefers_http1(CHATGPT)

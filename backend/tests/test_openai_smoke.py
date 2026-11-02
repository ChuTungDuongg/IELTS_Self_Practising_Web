import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from test_openai_integration import settings


def script():
    path = Path(__file__).parents[2] / "scripts/smoke_openai.py"
    spec = importlib.util.spec_from_file_location("openai_smoke_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_requires_explicit_paid_opt_in_before_reading_credentials(monkeypatch):
    module = script()
    monkeypatch.setattr(module, "Settings", lambda **_: pytest.fail("must not read credentials"))
    with pytest.raises(SystemExit) as error:
        module.main([])
    assert error.value.code == 2


@pytest.mark.parametrize("status", [200, 401])
def test_smoke_is_one_paid_post_with_safe_machine_readable_result(monkeypatch, capsys, status):
    module = script()
    monkeypatch.setattr(module, "Settings", lambda **_: settings())
    requests = []

    def handler(request):
        requests.append(request)
        body = json.loads(request.content)
        assert body["max_completion_tokens"] == 64
        return httpx.Response(
            status,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": '{"ready":true}'}}],
                "usage": {"total_tokens": 17},
                "error": {"message": "fictional-private-key private body"},
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
    )
    result = module.main(["--allow-paid-request"])
    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert parsed["status"] == ("PASS" if status == 200 else "FAIL")
    assert result == (0 if status == 200 else 1)
    assert len(requests) == 1 and requests[0].method == "POST"
    assert "fictional-private-key" not in output and "private body" not in output
    assert parsed["modal_deployment"] == "NOT_VERIFIED"

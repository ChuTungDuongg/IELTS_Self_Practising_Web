"""Test the isolated endpoint and generation bounds without Transformers/GPU."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from app.schemas.chart_cross_check import DEPLOT_MODEL, DEPLOT_REVISION


@pytest.fixture
def chart_runtime(monkeypatch):
    modal = MagicMock()
    for decorator in ["function", "asgi_app"]:
        (modal.App.return_value if decorator == "function" else modal).__getattr__(
            decorator
        ).return_value = lambda function: function
    monkeypatch.setitem(sys.modules, "modal", modal)
    spec = importlib.util.spec_from_file_location(
        "deplot_runtime_test",
        Path(__file__).resolve().parents[2] / "deploy/modal/chart_derenderer.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.MODEL == DEPLOT_MODEL and module.REVISION == DEPLOT_REVISION
    loader = MagicMock(return_value=(object(), object(), object()))
    monkeypatch.setattr(module, "load_model", loader)
    return module, modal, loader


@pytest.mark.parametrize(
    "case,status", [("valid", 200), ("format", 415), ("oversize", 413), ("failure", 422)]
)
async def test_protected_single_model_endpoint_checks_bounds_and_safe_errors(
    chart_runtime, monkeypatch, case, status
):
    module, modal, loader = chart_runtime
    calls = []

    def extract(content, *args):
        calls.append(content)
        if case == "failure":
            raise RuntimeError("fictional private payload")
        return "Item | Value\nA | 48"

    monkeypatch.setattr(module, "extract_table", extract)
    api = module.serve()
    body = b"x" * (10 * 1024 * 1024 + 1) if case == "oversize" else b"synthetic trusted image"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://test"
    ) as client:
        response = await client.post(
            "/extract",
            content=body,
            headers={"Content-Type": "image/svg+xml" if case == "format" else "image/png"},
        )
    assert response.status_code == status
    assert "private" not in response.text
    loader.assert_called_once()
    modal.asgi_app.assert_called_once_with(requires_proxy_auth=True)
    if status == 200:
        assert response.json() == {
            "table": "Item | Value\nA | 48",
            "model": module.MODEL,
            "revision": module.REVISION,
        }
    if status in {413, 415}:
        assert not calls


@pytest.mark.parametrize(
    "eos,table,error",
    [
        (1, "Item | Value\nA | 48", None),
        (2, "Item | Value\nA | 48", "Incomplete"),
        (1, "x" * 16385, "too large"),
    ],
)
def test_model_output_must_finish_and_stay_bounded(chart_runtime, monkeypatch, eos, table, error):
    from contextlib import nullcontext
    from types import SimpleNamespace

    module, _, _ = chart_runtime
    source = MagicMock(format="PNG", width=100, height=100)
    source.__enter__.return_value = source
    pil = MagicMock()
    pil.Image.DecompressionBombWarning = type("DecompressionBombWarning", (Warning,), {})
    pil.Image.open.return_value = source
    monkeypatch.setitem(sys.modules, "PIL", pil)
    processor = MagicMock()
    processor.return_value.to.return_value = {}
    processor.decode.return_value = table
    generated = MagicMock()
    generated.__getitem__.return_value.item.return_value = eos
    model = MagicMock(device="cuda", generation_config=SimpleNamespace(eos_token_id=1))
    model.generate.return_value = generated
    torch = SimpleNamespace(inference_mode=nullcontext)
    if error:
        with pytest.raises(ValueError, match=error):
            module.extract_table(b"synthetic", processor, model, torch)
    else:
        assert module.extract_table(b"synthetic", processor, model, torch) == table
    model.generate.assert_called_once_with(max_new_tokens=512)

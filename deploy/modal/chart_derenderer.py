"""Isolated scale-to-zero DePlot image service; no essay or IELTS scoring."""

import modal

MODEL = "google/deplot"
REVISION = "6e76d62430da16986be3426bae32301fb9115397"
TRANSFORMERS_VERSION = "5.13.0"
app = modal.App("ielts-chart-derenderer")
cache = modal.Volume.from_name("ielts-deplot-model-cache", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "torch==2.10.0",
        f"transformers=={TRANSFORMERS_VERSION}",
        "Pillow==12.1.1",
        "sentencepiece==0.2.1",
        "fastapi==0.135.1",
    )
    .env({"HF_HOME": "/cache/huggingface", "HF_HUB_DISABLE_TELEMETRY": "1"})
)


def load_model():
    import torch
    from transformers import AutoProcessor, Pix2StructForConditionalGeneration

    processor = AutoProcessor.from_pretrained(MODEL, revision=REVISION)
    model = (
        Pix2StructForConditionalGeneration.from_pretrained(MODEL, revision=REVISION)
        .to("cuda")
        .eval()
    )
    return processor, model, torch


def extract_table(content, processor, model, torch):
    import io
    import warnings

    from PIL import Image

    if not 0 < len(content) <= 10 * 1024 * 1024:
        raise ValueError("Invalid image size")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(content)) as source:
            if (
                source.format not in {"PNG", "JPEG", "WEBP"}
                or source.width * source.height > 12_000_000
            ):
                raise ValueError("Invalid image")
            picture = source.convert("RGB")
    inputs = processor(
        images=picture,
        text="Generate underlying data table of the figure below:",
        return_tensors="pt",
    ).to(model.device)
    with torch.inference_mode():
        generated = model.generate(**inputs, max_new_tokens=512)
    eos = model.generation_config.eos_token_id
    eos_ids = eos if isinstance(eos, list) else [eos]
    if generated[0, -1].item() not in eos_ids:
        raise ValueError("Incomplete chart table")
    table = processor.decode(generated[0], skip_special_tokens=True)
    if len(table) > 16384:
        raise ValueError("Chart table too large")
    return table


@app.function(
    image=image,
    gpu="T4",
    cpu=2,
    memory=8192,
    volumes={"/cache": cache},
    min_containers=0,
    max_containers=1,
    scaledown_window=60,
    timeout=240,
)
@modal.asgi_app(requires_proxy_auth=True)
def serve():
    import asyncio

    from fastapi import FastAPI, HTTPException, Request

    processor, model, torch = load_model()
    api = FastAPI()
    lock = asyncio.Lock()

    @api.post("/extract")
    async def extract(request: Request):
        if request.headers.get("content-type") not in {"image/png", "image/jpeg", "image/webp"}:
            raise HTTPException(415, "Unsupported image")
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > 10 * 1024 * 1024:
                raise HTTPException(413, "Image too large")
        async with lock:
            try:
                table = await asyncio.to_thread(
                    extract_table, bytes(content), processor, model, torch
                )
            except Exception:
                raise HTTPException(422, "Chart extraction unavailable") from None
        return {"table": table, "model": MODEL, "revision": REVISION}

    return api


@app.function(image=image, gpu="T4", cpu=2, memory=8192, volumes={"/cache": cache}, timeout=240)
def synthetic_smoke():
    """One optional original multi-pie extraction; reuse returned table locally."""
    import io
    import time

    from PIL import Image, ImageDraw

    picture = Image.new("RGB", (960, 460), "white")
    draw = ImageDraw.Draw(picture)
    colours = ["#4978bf", "#e39748", "#62a882"]
    for left, region, values in [(50, "Region A", [60, 25, 15]), (520, "Region B", [30, 50, 20])]:
        draw.text((left + 80, 20), region, fill="black", font_size=24)
        start = 0
        for colour, value in zip(colours, values, strict=True):
            draw.pieslice((left, 70, left + 280, 350), start, start + value * 3.6, fill=colour)
            start += value * 3.6
        for y, label, value in zip(
            [365, 392, 419], ["Agriculture", "Industry", "Domestic"], values, strict=True
        ):
            draw.text((left, y), f"{label}: {value}%", fill="black", font_size=20)
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG")
    started = time.monotonic()
    processor, model, torch = load_model()
    loaded = time.monotonic()
    table = extract_table(buffer.getvalue(), processor, model, torch)
    return {
        "table": table,
        "load_seconds": loaded - started,
        "inference_seconds": time.monotonic() - loaded,
        "gpu_peak_bytes": torch.cuda.max_memory_allocated(),
        "model": MODEL,
        "revision": REVISION,
    }

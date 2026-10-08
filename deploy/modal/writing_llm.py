"""One protected Ministral 3 text/vision service, included by the web entry point."""

import subprocess

import modal

MODEL = "mistralai/Ministral-3-8B-Instruct-2512"
app = modal.App("ielts-writing-llm")
cache = modal.Volume.from_name("ielts-writing-model-cache", create_if_missing=True)
image = (
    modal.Image.from_registry("vllm/vllm-openai:v0.13.0", add_python="3.12")
    .entrypoint([])
    .env(
        {
            "HF_HOME": "/cache/huggingface",
            "VLLM_CACHE_ROOT": "/cache/vllm",
            "HF_XET_HIGH_PERFORMANCE": "1",
        }
    )
)


@app.function(
    image=image,
    gpu="L4",
    cpu=4,
    memory=32768,
    volumes={"/cache": cache},
    min_containers=0,
    max_containers=1,
    scaledown_window=60,
    timeout=900,
)
@modal.web_server(8000, startup_timeout=600, requires_proxy_auth=True)
def serve():
    subprocess.Popen(
        [
            "vllm",
            "serve",
            MODEL,
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--tokenizer-mode",
            "mistral",
            "--config-format",
            "mistral",
            "--load-format",
            "mistral",
            "--dtype",
            "auto",
            "--max-model-len",
            "8192",
            "--max-num-seqs",
            "1",
            "--limit-mm-per-prompt",
            '{"image": 1}',
            "--gpu-memory-utilization",
            "0.90",
            "--enforce-eager",
            "--disable-log-requests",
            "--disable-uvicorn-access-log",
        ]
    )

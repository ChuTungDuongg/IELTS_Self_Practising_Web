"""Protected, scale-to-zero Task 2 inference. See docs/ai-writing.md."""

import subprocess

import modal

MODEL = "mistralai/Ministral-8B-Instruct-2410"
app = modal.App("ielts-writing-llm")
cache = modal.Volume.from_name("ielts-writing-model-cache", create_if_missing=True)
image = (
    modal.Image.from_registry("vllm/vllm-openai:v0.11.2", add_python="3.12")
    .entrypoint([])
    .env({"HF_HOME": "/cache/huggingface", "VLLM_CACHE_ROOT": "/cache/vllm"})
)


@app.function(
    image=image,
    gpu="L4",
    cpu=2,
    memory=8192,
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
            "half",
            "--max-model-len",
            "8192",
            "--max-num-seqs",
            "2",
            "--gpu-memory-utilization",
            "0.90",
            "--enforce-eager",
            "--disable-log-requests",
        ]
    )

"""One protected Ministral 3 text/vision service, included by the web entry point."""

import os
import subprocess

import modal
from deploy.modal.writing_llm_config import MODEL as MODEL
from deploy.modal.writing_llm_config import WritingServingConfig

config = WritingServingConfig.from_env(os.environ)
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
            **config.image_env(),
        }
    )
    .add_local_python_source("deploy.modal")
)


@app.function(
    image=image,
    gpu="L4",
    cpu=4,
    memory=32768,
    volumes={"/cache": cache},
    min_containers=0,
    max_containers=1,
    scaledown_window=config.scaledown_seconds,
    timeout=900,
)
@modal.concurrent(max_inputs=config.max_num_seqs)
@modal.web_server(8000, startup_timeout=600, requires_proxy_auth=True)
def serve():
    subprocess.Popen(config.command())

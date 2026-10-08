"""Non-secret deploy-time serving settings, importable without Modal or a GPU."""

from collections.abc import Mapping
from dataclasses import dataclass

MODEL = "mistralai/Ministral-3-8B-Instruct-2512"


@dataclass(frozen=True)
class WritingServingConfig:
    max_num_seqs: int = 2
    profile: str = "cost"
    scaledown_seconds: int = 60

    @classmethod
    def from_env(cls, env: Mapping[str, str]):
        profile = env.get("IELTS_WRITING_LLM_PROFILE", "cost")
        if profile not in {"cost", "interactive"}:
            raise ValueError("Writing LLM profile must be cost or interactive")
        sequences = int(env.get("IELTS_WRITING_LLM_MAX_NUM_SEQS", "2"))
        if sequences not in {1, 2, 4}:
            raise ValueError("Writing LLM max-num-seqs must be 1, 2 or 4")
        scaledown = int(
            env.get(
                "IELTS_WRITING_LLM_SCALEDOWN_SECONDS", "300" if profile == "interactive" else "60"
            )
        )
        if not 60 <= scaledown <= 900:
            raise ValueError("Writing LLM scaledown must be between 60 and 900 seconds")
        return cls(sequences, profile, scaledown)

    def image_env(self) -> dict[str, str]:
        # Freeze host configuration into the image for consistent remote imports.
        return {
            "IELTS_WRITING_LLM_MAX_NUM_SEQS": str(self.max_num_seqs),
            "IELTS_WRITING_LLM_PROFILE": self.profile,
            "IELTS_WRITING_LLM_SCALEDOWN_SECONDS": str(self.scaledown_seconds),
        }

    def command(self) -> list[str]:
        return [
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
            str(self.max_num_seqs),
            "--limit-mm-per-prompt",
            '{"image": 1}',
            "--gpu-memory-utilization",
            "0.90",
            "--enforce-eager",
            "--disable-log-requests",
            "--disable-uvicorn-access-log",
        ]

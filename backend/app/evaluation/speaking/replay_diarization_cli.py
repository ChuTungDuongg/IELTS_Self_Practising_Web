"""CLI-only composition; imported lazily, with no changes to production provider selection."""

import getpass
import os
import sys

from dotenv import dotenv_values

from app.evaluation.speaking.diarization_backend import LocalDiarizer
from app.evaluation.speaking.manifest import BenchmarkInputError
from app.evaluation.speaking.replay_cache import read_checkpoint
from app.evaluation.speaking.replay_diarization import auto_segment
from app.evaluation.speaking.replay_segment_review import (
    approve_segments,
    review_summary,
    update_review,
)


def run_diarization_action(root, settings, config, args):
    updates = (
        args.confirm_candidate_speaker
        or args.set_part_boundaries
        or args.confirm_file_parts
        or args.question_context
        or args.edit_segment
        or args.exclude_segment
        or args.acknowledge_segment
    )
    if args.setup_diarization_model and (
        args.auto_segment
        or args.review_segments
        or updates
        or args.approve_segments
        or args.diagnose_diarization
    ):
        raise BenchmarkInputError("REPLAY_MODE_CONFLICT")
    if args.diagnose_diarization and (
        args.auto_segment or args.review_segments or updates or args.approve_segments
    ):
        raise BenchmarkInputError("REPLAY_MODE_CONFLICT")
    if args.auto_segment and (updates or args.approve_segments):
        raise BenchmarkInputError("REPLAY_MODE_CONFLICT")
    if args.setup_diarization_model or args.auto_segment or args.diagnose_diarization:
        options = {}
        if args.diarization_config:
            path = args.diarization_config.resolve()
            if not path.is_relative_to(root.resolve()):
                raise BenchmarkInputError("REPLAY_PRIVATE_ROOT_REQUIRED")
            options = read_checkpoint(path) or {}
            options.pop("schema_version", None)
        pause_tolerance = options.pop("pause_tolerance_ms", 3000)
        backend = LocalDiarizer(
            python=args.diarization_python,
            model_dir=args.diarization_model_dir,
            device=args.diarization_device,
            **options,
        )
        if args.setup_diarization_model or args.diagnose_diarization:
            print("Checking isolated diarization environment and local model storage...")
            checked = backend.preflight()
            print("Python 3.12 / pinned packages / Torch / TorchCodec / pyannote: OK")
            major = checked.get("ffmpeg_shared_major")
            print(
                f"FFmpeg shared libraries: {major if major else 'system runtime'}; native imports: OK"
            )
            print(f"Model cache: {checked['model_state']}")
            if args.diagnose_diarization:
                print("Offline preflight complete. No token requested or provider called.")
                return
            if checked["model_state"] == "VERIFIED":
                print(
                    "Diarization model ready; verified existing assets, no download or token needed."
                )
                return
            token = os.environ.get("HF_TOKEN") or dotenv_values(config, interpolate=False).get(
                "HF_TOKEN"
            )
            if not token and sys.stdin.isatty():
                token = getpass.getpass("Private Hugging Face token (not echoed): ")
            if not token:
                raise BenchmarkInputError("REPLAY_DIARIZATION_HF_TOKEN_REQUIRED")
            print("Downloading pinned Community-1 and verifying model assets...")
            backend.setup(token)
            print("Diarization model ready. No Azure/OpenAI request made.")
            return
        proposal, reused = auto_segment(
            root, settings, backend=backend, pause_tolerance_ms=pause_tolerance
        )
        print(
            f"Local diarization: {len(proposal.sources)} files; {reused} cached; {len(proposal.segments)} proposed windows."
        )
        print(
            "Wrote private diarization.json and segments.proposed.json; grading manifest unchanged."
        )
    if updates:
        update_review(
            root,
            candidate=args.confirm_candidate_speaker,
            part_boundaries=args.set_part_boundaries,
            file_parts=args.confirm_file_parts,
            questions=args.question_context,
            edit=args.edit_segment,
            exclude=args.exclude_segment,
            acknowledge=args.acknowledge_segment,
        )
    if args.approve_segments:
        manifest = approve_segments(root, settings)
        print(
            f"Approved {len(manifest.segments)} candidate responses into segments.json; no provider calls."
        )
    print(review_summary(root))

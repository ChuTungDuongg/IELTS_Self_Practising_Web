"""One lightweight inference, using backend-only proxy tokens from the environment."""

import argparse
import json
import os
import urllib.error
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True, help="Protected endpoint URL including /v1")
    args = parser.parse_args()
    headers = {
        "Content-Type": "application/json",
        "Modal-Key": os.environ["AI_WRITING_MODAL_KEY"],
        "Modal-Secret": os.environ["AI_WRITING_MODAL_SECRET"],
    }
    body = {
        "model": "mistralai/Ministral-8B-Instruct-2410",
        "messages": [{"role": "user", "content": 'Return only this JSON object: {"ready": true}'}],
        "temperature": 0,
        "max_tokens": 16,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        args.base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=660) as response:
            result = json.load(response)
        content = json.loads(result["choices"][0]["message"]["content"])
        if content != {"ready": True}:
            raise ValueError("Unexpected smoke result")
        print("Smoke inference passed: ready=true")
    except urllib.error.HTTPError as exc:
        raise SystemExit(
            f"Smoke inference failed: HTTP {exc.code}; inspect Modal server logs."
        ) from None
    except (ValueError, KeyError, IndexError, urllib.error.URLError):
        raise SystemExit("Smoke inference failed; inspect Modal server logs.") from None


if __name__ == "__main__":
    main()

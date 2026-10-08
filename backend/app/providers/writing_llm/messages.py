"""OpenAI-compatible serialization, shared by the two transport adapters.

Verified against vLLM v0.13.0's multimodal chat client and the Ministral 3
model card. No placeholders, remote URLs, or additional image messages.
"""

import base64
from typing import Any

from app.providers.writing_llm.base import ImagePart, Message


def serialize_messages(messages: list[Message]) -> list[dict[str, Any]]:
    images = sum(
        isinstance(part, ImagePart)
        for message in messages
        if isinstance(message["content"], list)
        for part in message["content"]
    )
    if images > 1:
        raise ValueError("At most one trusted image per request")
    serialized = []
    for message in messages:
        content = message["content"]
        if isinstance(content, str):
            serialized.append({"role": message["role"], "content": content})
            continue
        parts = []
        for part in content:
            if isinstance(part, ImagePart):
                encoded = base64.b64encode(part.data).decode("ascii")
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{part.mime_type};base64,{encoded}",
                        },
                    }
                )
            elif part.get("type") == "text" and isinstance(part.get("text"), str):
                parts.append({"type": "text", "text": part["text"]})
            else:
                raise ValueError("Unsupported content part")
        serialized.append({"role": message["role"], "content": parts})
    return serialized

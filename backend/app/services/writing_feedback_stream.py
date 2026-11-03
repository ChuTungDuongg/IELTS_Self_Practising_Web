"""Provisional business text only; complete JSON still owns validation and results."""

import json
from time import monotonic

from app.schemas.writing_ai import EventPayload


class FeedbackPreviewText:
    """Incremental JSON string scanner; never extracts IDs, scores or reasoning."""

    def __init__(self):
        self.token = None
        self.capture = self.escaped = self.pending = False
        self.last_string = ""
        self.completed = []

    @staticmethod
    def decode(prefix):
        # A chunk may split a JSON escape or a UTF-16 surrogate pair.
        for trim in range(min(6, len(prefix)) + 1):
            raw = prefix[:-trim] if trim else prefix
            try:
                value = json.loads('"' + raw + '"')
                return value.encode("utf-16", "surrogatepass").decode("utf-16", "ignore")
            except (ValueError, UnicodeError):
                pass
        return ""

    def feed(self, content):
        for char in content:
            if self.token is not None:
                if char == '"' and not self.escaped:
                    value = self.decode(self.token)
                    if self.capture:
                        self.completed.append(value)
                    self.last_string = value
                    self.token = None
                    self.capture = False
                    continue
                self.token += char
                self.escaped = char == "\\" and not self.escaped
            elif char == '"':
                self.token, self.capture, self.escaped = "", self.pending, False
                self.pending = False
            elif char == ":":
                self.pending = self.last_string in {"observation", "feedback"}
            elif not char.isspace():
                self.pending = False
        partial = [self.decode(self.token)] if self.capture and self.token is not None else []
        return "\n\n".join([*self.completed, *partial])[:4000]


class FeedbackPreview:
    def __init__(self, trait, trace):
        self.trait, self.trace = trait, trace
        self.parser = FeedbackPreviewText()
        self.text = self.sent = ""
        self.count = 0
        self.last_sent = 0

    async def feed(self, content):
        if content is None:
            self.parser = FeedbackPreviewText()
            self.text = self.sent = ""
            await self.emit("")  # Explicit reset before an initial/repair POST.
            return
        self.text = self.parser.feed(content)
        if (
            self.count < 100
            and self.text != self.sent
            and (
                not self.sent
                or (len(self.text) - len(self.sent) >= 12 and monotonic() - self.last_sent >= 0.1)
            )
        ):
            await self.emit(self.text)

    async def flush(self):
        if self.text != self.sent:
            await self.emit(self.text)

    async def emit(self, text):
        await self.trace(
            "criterion.feedback.draft",
            EventPayload(criterion=self.trait, stage="feedback", feedback_preview=text),
        )
        self.sent, self.last_sent = text, monotonic()
        self.count += 1

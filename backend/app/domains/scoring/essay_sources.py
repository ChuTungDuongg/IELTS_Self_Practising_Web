"""Deterministic essay anchors. Offsets are original Python character indices.

By default, blank lines separate paragraphs and one line break may wrap a
sentence. Textarea mode treats each explicit line break as a paragraph boundary;
visual soft wrapping adds no break to saved content. IDs number non-empty
paragraphs/sentences in source order. Abbreviations are handled conservatively:
merging an ambiguous boundary is safer than inventing a slice. No Unicode,
punctuation, spelling or internal whitespace is rewritten.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.domains.scoring.writing import WritingScoringRequest

type ParagraphMode = Literal["blank_lines", "textarea"]

_NEWLINE = r"(?:\r\n|(?<!\r)\n|\r(?!\n))"
_PARAGRAPH_BREAK = re.compile(rf"{_NEWLINE}[ \t]*(?:{_NEWLINE}[ \t]*)+")
_TEXTAREA_PARAGRAPH_BREAK = re.compile(rf"{_NEWLINE}[ \t]*")
_ABBREVIATIONS = {
    "mr",
    "mrs",
    "ms",
    "dr",
    "prof",
    "sr",
    "jr",
    "st",
    "vs",
    "etc",
    "e.g",
    "i.e",
    "u.s",
    "u.k",
    "a.m",
    "p.m",
    "no",
    "fig",
}
_TERMINATORS = ".!?。！？…"
_CLOSERS = "\"'”’»)]}"


@dataclass(frozen=True)
class SourceSegment:
    source_id: str
    paragraph_index: int
    sentence_index: int
    start: int
    end: int
    text: str


def _period_is_internal(essay: str, index: int, paragraph_start: int) -> bool:
    if (
        index
        and index + 1 < len(essay)
        and essay[index - 1].isdigit()
        and essay[index + 1].isdigit()
    ):
        return True
    token = re.search(r"([A-Za-z]+(?:\.[A-Za-z]+)*)\.$", essay[paragraph_start : index + 1])
    if token:
        word = token[1]
        return (
            word.lower() in _ABBREVIATIONS
            or len(word) == 1
            or bool(re.fullmatch(r"(?:[A-Za-z]\.)+[A-Za-z]", word))
        )
    return False


def segment_essay(
    essay: str, *, paragraph_mode: ParagraphMode = "blank_lines"
) -> list[SourceSegment]:
    if paragraph_mode == "blank_lines":
        paragraph_break = _PARAGRAPH_BREAK
    elif paragraph_mode == "textarea":
        paragraph_break = _TEXTAREA_PARAGRAPH_BREAK
    else:
        raise ValueError("Unsupported essay paragraph mode")
    segments: list[SourceSegment] = []
    paragraph_start = 0
    paragraph_index = 0
    boundaries = [match.span() for match in paragraph_break.finditer(essay)] + [
        (len(essay), len(essay))
    ]
    for paragraph_end, next_start in boundaries:
        start, end = paragraph_start, paragraph_end
        while start < end and essay[start].isspace():
            start += 1
        while end > start and essay[end - 1].isspace():
            end -= 1
        paragraph_start = next_start
        if start == end:
            continue
        paragraph_index += 1
        sentence_index = 0
        sentence_start = start
        index = start
        while index < end:
            if essay[index] not in _TERMINATORS or (
                essay[index] == "." and _period_is_internal(essay, index, start)
            ):
                index += 1
                continue
            boundary = index + 1
            while boundary < end and essay[boundary] in _TERMINATORS + _CLOSERS:
                boundary += 1
            if boundary < end and not essay[boundary].isspace():
                index += 1
                continue
            sentence_index += 1
            segments.append(
                SourceSegment(
                    f"P{paragraph_index}S{sentence_index}",
                    paragraph_index,
                    sentence_index,
                    sentence_start,
                    boundary,
                    essay[sentence_start:boundary],
                )
            )
            sentence_start = boundary
            while sentence_start < end and essay[sentence_start].isspace():
                sentence_start += 1
            index = sentence_start
        if sentence_start < end:
            sentence_index += 1
            segments.append(
                SourceSegment(
                    f"P{paragraph_index}S{sentence_index}",
                    paragraph_index,
                    sentence_index,
                    sentence_start,
                    end,
                    essay[sentence_start:end],
                )
            )
    return segments


def request_sources(request: WritingScoringRequest) -> list[SourceSegment]:
    """Use the request's input provenance consistently at every scoring stage."""
    return segment_essay(request.response, paragraph_mode=request.paragraph_mode)

import pytest

from app.domains.scoring.essay_sources import segment_essay


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_paragraph_sentence_ids_offsets_and_repeated_text(newline):
    essay = f"  Parks help.  Parks help!{newline}A wrapped line?{newline}{newline} \t{newline}They matter.  "
    segments = segment_essay(essay)
    assert [(s.source_id, s.paragraph_index, s.sentence_index, s.text) for s in segments] == [
        ("P1S1", 1, 1, "Parks help."),
        ("P1S2", 1, 2, "Parks help!"),
        ("P1S3", 1, 3, "A wrapped line?"),
        ("P2S1", 2, 1, "They matter."),
    ]
    assert segments == segment_essay(essay)
    assert len({s.source_id for s in segments}) == len(segments)
    for segment in segments:
        assert segment.text == essay[segment.start : segment.end]


@pytest.mark.parametrize(
    "essay,texts",
    [
        ("“It’s useful!”  She agreed. Isn't it?", ["“It’s useful!”", "She agreed.", "Isn't it?"]),
        (
            "A café—small but useful–helps.  It  matters… Yes！ Why？",
            ["A café—small but useful–helps.", "It  matters…", "Yes！", "Why？"],
        ),
        (
            "Dr. Smith cites e.g. parks in the U.S. as useful. Costs are 3.5 units.",
            ["Dr. Smith cites e.g. parks in the U.S. as useful.", "Costs are 3.5 units."],
        ),
        ("No punctuation\nwith  multiple spaces", ["No punctuation\nwith  multiple spaces"]),
        ("Same. Same.\n\nSame.", ["Same.", "Same.", "Same."]),
        ("\n\r\n \t ", []),
    ],
)
def test_exact_unicode_and_conservative_abbreviations(essay, texts):
    segments = segment_essay(essay)
    assert [s.text for s in segments] == texts
    for segment in segments:
        assert essay[segment.start : segment.end] == segment.text

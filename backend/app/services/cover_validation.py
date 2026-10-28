"""Validate cover signatures and bound decoded image dimensions without decoding pixels."""

import zlib

from app.providers.writing_llm.base import ImagePart

MAX_DIMENSION = 16_384
MAX_PIXELS = 40_000_000
JPEG_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def validate_cover_image(mime: str, data: bytes) -> None:
    ImagePart(mime, data)
    width, height = _dimensions(mime, data)
    if not (
        0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION and width * height <= MAX_PIXELS
    ):
        raise ValueError("Cover image dimensions are invalid or too large")


def _dimensions(mime: str, data: bytes) -> tuple[int, int]:
    if mime == "image/png":
        if len(data) < 33 or data[8:16] != b"\x00\x00\x00\rIHDR":
            raise ValueError("Invalid PNG header")
        width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        offset = 8
        saw_data = False
        while offset + 12 <= len(data):
            size = int.from_bytes(data[offset : offset + 4], "big")
            end = offset + 12 + size
            if end > len(data):
                raise ValueError("Truncated PNG chunk")
            kind = data[offset + 4 : offset + 8]
            checksum = int.from_bytes(data[end - 4 : end], "big")
            if zlib.crc32(data[offset + 4 : end - 4]) != checksum:
                raise ValueError("Invalid PNG checksum")
            saw_data |= kind == b"IDAT" and size > 0
            if kind == b"IEND":
                if size != 0 or end != len(data) or not saw_data:
                    raise ValueError("Invalid PNG end")
                return width, height
            offset = end
        raise ValueError("PNG is incomplete")
    if mime == "image/webp":
        if len(data) < 30 or int.from_bytes(data[4:8], "little") + 8 > len(data):
            raise ValueError("Invalid WebP header")
        kind = data[12:16]
        chunk_size = int.from_bytes(data[16:20], "little")
        if chunk_size == 0 or 20 + chunk_size > len(data):
            raise ValueError("Invalid WebP chunk")
        if kind == b"VP8X":
            return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(
                data[27:30], "little"
            )
        if kind == b"VP8L" and data[20] == 0x2F:
            bits = int.from_bytes(data[21:25], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if kind == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            return int.from_bytes(data[26:28], "little") & 0x3FFF, int.from_bytes(
                data[28:30], "little"
            ) & 0x3FFF
        raise ValueError("Invalid WebP image")
    if mime == "image/jpeg":
        if b"\xff\xda" not in data or b"\xff\xd9" not in data:
            raise ValueError("JPEG is incomplete")
        offset = 2
        while offset + 4 <= len(data):
            if data[offset] != 0xFF:
                raise ValueError("Invalid JPEG marker")
            while offset < len(data) and data[offset] == 0xFF:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in {0xD8, 0xD9, 0x01} or 0xD0 <= marker <= 0xD7:
                continue
            if offset + 2 > len(data):
                break
            size = int.from_bytes(data[offset : offset + 2], "big")
            if size < 2 or offset + size > len(data):
                break
            if marker in JPEG_SOF and size >= 7:
                return int.from_bytes(data[offset + 5 : offset + 7], "big"), int.from_bytes(
                    data[offset + 3 : offset + 5], "big"
                )
            if marker == 0xDA:
                break
            offset += size
    raise ValueError("Image dimensions could not be determined")

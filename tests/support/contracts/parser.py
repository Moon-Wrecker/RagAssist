"""Contract for document ``Parser`` adapters (the Parser port in knowledge/domain).

The port: ``supports(mime) -> bool`` and ``parse(content, *, mime, filename) -> ParsedDocument``, where a
ParsedDocument holds ``Block`` objects (``kind``, ``text``, ``heading_path``, ``page``).

Subclasses set ``mimes`` (what the parser must support), ``sample`` (bytes of a small document with a heading,
a paragraph and a table, or None), ``corrupt`` (bytes that are not valid for the format, or None) and
``unicode_in_sample`` (False when the sample cannot carry non-ASCII text, e.g. PDF fixtures).
"""

from __future__ import annotations

import pytest

from support.specs import need


class ParserContract:
    mimes: tuple[str, ...] = ()
    sample: bytes | None = None
    corrupt: bytes | None = None
    sample_filename: str = "sample.bin"
    unicode_in_sample: bool = True

    @pytest.fixture
    def parser(self):  # type: ignore[no-untyped-def]  # pragma: no cover - overridden
        raise NotImplementedError

    @pytest.fixture
    def parse_error(self):  # type: ignore[no-untyped-def]
        return need("knowledge.ParseError")

    def test_supports_every_declared_mime(self, parser) -> None:  # type: ignore[no-untyped-def]
        for mime in self.mimes:
            assert parser.supports(mime), mime

    def test_rejects_an_unrelated_mime(self, parser) -> None:  # type: ignore[no-untyped-def]
        assert parser.supports("application/x-not-a-document") is False

    def test_has_a_name(self, parser) -> None:  # type: ignore[no-untyped-def]
        assert isinstance(parser.name, str) and parser.name

    async def test_parsing_is_deterministic(self, parser) -> None:  # type: ignore[no-untyped-def]
        if self.sample is None:
            pytest.skip("no sample document for this format")
        mime = self.mimes[0]
        first = await parser.parse(self.sample, mime=mime, filename=self.sample_filename)
        second = await parser.parse(self.sample, mime=mime, filename=self.sample_filename)
        assert first == second

    async def test_blocks_carry_text_and_a_heading_path(self, parser) -> None:  # type: ignore[no-untyped-def]
        if self.sample is None:
            pytest.skip("no sample document for this format")
        parsed = await parser.parse(self.sample, mime=self.mimes[0], filename=self.sample_filename)
        assert parsed.blocks, "a non-empty document must produce blocks"
        for block in parsed.blocks:
            assert isinstance(block.text, str)
            assert isinstance(block.heading_path, tuple)

    async def test_unicode_text_survives_parsing(self, parser) -> None:  # type: ignore[no-untyped-def]
        if self.sample is None or not self.unicode_in_sample:
            pytest.skip("no sample document with non-ASCII text for this format")
        parsed = await parser.parse(self.sample, mime=self.mimes[0], filename=self.sample_filename)
        assert any("é" in b.text or "日本語" in b.text or "Café" in b.text for b in parsed.blocks)

    async def test_empty_input_gives_no_blocks_or_a_parse_error(self, parser, parse_error) -> None:  # type: ignore[no-untyped-def]
        try:
            parsed = await parser.parse(b"", mime=self.mimes[0], filename="empty")
        except parse_error:
            return
        assert list(parsed.blocks) == []

    async def test_corrupt_input_raises_a_parse_error(self, parser, parse_error) -> None:  # type: ignore[no-untyped-def]
        if self.corrupt is None:
            pytest.skip("this format has no corrupt sample")
        with pytest.raises(parse_error):
            await parser.parse(self.corrupt, mime=self.mimes[0], filename="corrupt")

    async def test_invalid_utf8_never_escapes_as_a_decode_error(self, parser, parse_error) -> None:  # type: ignore[no-untyped-def]
        raw = "café résumé".encode("latin-1")  # not valid UTF-8
        try:
            parsed = await parser.parse(raw, mime=self.mimes[0], filename="latin1")
        except parse_error:
            return
        assert isinstance(parsed.blocks, (list, tuple))

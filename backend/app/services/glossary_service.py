from __future__ import annotations

import re

from app.core.config import Settings
from app.schemas.glossary import GlossaryTerm
from app.schemas.transcript import TranscriptItem
from app.services.glossary_store_service import GlossaryStoreService


class GlossaryService:
    MAX_TERMS = 50

    def __init__(self, settings: Settings, glossary_store_service: GlossaryStoreService | None = None) -> None:
        self._settings = settings
        self._default_terms = self.parse_terms(settings.custom_glossary_terms)
        self._glossary_store_service = glossary_store_service

    def resolve_terms(self, raw_terms: str | None) -> list[GlossaryTerm]:
        terms = [
            *self.parse_terms(raw_terms),
            *self._list_persisted_terms(),
            *self._default_terms,
        ]
        deduped: list[GlossaryTerm] = []
        seen: set[str] = set()
        for term in terms:
            key = term.term.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(term)
            if len(deduped) >= self.MAX_TERMS:
                break
        return deduped

    def _list_persisted_terms(self) -> list[GlossaryTerm]:
        if self._glossary_store_service is None:
            return []
        return [
            GlossaryTerm(term=record.term, replacement=record.replacement, note=record.note)
            for record in self._glossary_store_service.list_terms()
        ]

    def apply_to_transcripts(
        self,
        transcripts: list[TranscriptItem],
        terms: list[GlossaryTerm],
    ) -> list[TranscriptItem]:
        if not terms:
            return transcripts

        corrected: list[TranscriptItem] = []
        for transcript in transcripts:
            text = transcript.text
            for term in terms:
                if not term.replacement or term.replacement.casefold() == term.term.casefold():
                    continue
                text = self._replace_term(text, term.term, term.replacement)
            if text == transcript.text:
                corrected.append(transcript)
                continue
            corrected.append(transcript.model_copy(update={"text": text}))
        return corrected

    def build_prompt_hint(self, terms: list[GlossaryTerm]) -> str:
        if not terms:
            return ""
        lines = ["Custom terminology glossary:"]
        for term in terms:
            if term.replacement:
                line = f"- {term.term} => {term.replacement}"
            else:
                line = f"- {term.term}"
            if term.note:
                line = f"{line} ({term.note})"
            lines.append(line)
        return "\n".join(lines)

    @classmethod
    def parse_terms(cls, raw_terms: str | None) -> list[GlossaryTerm]:
        if not raw_terms:
            return []

        terms: list[GlossaryTerm] = []
        for raw_line in re.split(r"[\n;]+", raw_terms):
            line = " ".join(raw_line.split()).strip(" ,")
            if not line:
                continue

            term: GlossaryTerm | None = None
            for separator in ("=>", "->", "="):
                if separator in line:
                    left, right = line.split(separator, 1)
                    term = GlossaryTerm(term=left.strip(), replacement=right.strip())
                    break
            if term is None and ":" in line:
                left, right = line.split(":", 1)
                term = GlossaryTerm(term=left.strip(), note=right.strip())
            if term is None:
                term = GlossaryTerm(term=line)

            terms.append(term)
            if len(terms) >= cls.MAX_TERMS:
                break
        return terms

    @staticmethod
    def _replace_term(text: str, term: str, replacement: str) -> str:
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9' -]*[A-Za-z0-9]", term):
            pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", re.IGNORECASE)
        else:
            pattern = re.compile(re.escape(term), re.IGNORECASE)
        return pattern.sub(replacement, text)

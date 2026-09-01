"""Named, ordered block rules and their configurable thresholds."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from . import ruoli as R


@dataclass(frozen=True)
class BlockRuleThresholds:
    title_page_position: float = .15
    title_page_max_characters: int = 180
    synopsis_position: float = .03
    synopsis_min_characters: int = 250
    synopsis_max_characters: int = 4_000
    synopsis_min_questions: int = 2
    epigraph_max_characters: int = 1_500
    navigation_max_characters: int = 10_000
    navigation_min_links: int = 3
    navigation_max_characters_per_link: int = 120
    marginal_start: float = .12
    marginal_end: float = .88
    marginal_max_characters: int = 4_000
    backlist_max_characters: int = 20_000
    divider_max_document_characters: int = 300
    divider_max_block_characters: int = 120
    divider_max_caption_characters: int = 90
    internal_prose_start: float = .12
    internal_prose_end: float = .92
    internal_prose_min_characters: int = 600
    internal_prose_max_characters: int = 1_500
    internal_prose_max_links: int = 2
    internal_prose_min_characters_per_element: int = 120
    composite_opening_position: float = .08
    composite_opening_min_characters: int = 450
    composite_opening_max_characters: int = 3_000
    composite_opening_min_elements: int = 4
    composite_opening_max_links: int = 1
    composite_opening_min_sentences: int = 3
    discursive_appendix_min_characters: int = 1_000
    discursive_appendix_min_characters_per_element: int = 180
    discursive_appendix_max_links: int = 2
    thematic_note_min_characters: int = 300
    thematic_note_max_links: int = 1
    thematic_note_min_characters_per_element: int = 120
    weak_index_min_characters: int = 800
    weak_index_min_characters_per_element: int = 300


DEFAULT_THRESHOLDS = BlockRuleThresholds()


@dataclass(frozen=True)
class RuleDecision:
    rule_id: str
    role: str
    confidence: float
    source: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class EvaluatedRule:
    matches: bool
    decision: RuleDecision


@dataclass(frozen=True)
class MarginalRuleContext:
    book_title: str | None
    document_name: str
    document_index: int
    document_blocks: int
    block_title: str | None
    block_text: str
    block_characters: int
    block_links: int
    block_elements: int
    block_markers: frozenset[str]
    position: float
    preliminary_title_role: str | None
    navigation_filename: bool
    thresholds: BlockRuleThresholds = DEFAULT_THRESHOLDS


Rule = Callable[[MarginalRuleContext], RuleDecision | None]


def _title_page(context: MarginalRuleContext) -> RuleDecision | None:
    threshold = context.thresholds
    title = R.normalizza(context.book_title or "").strip()
    if (title and context.position <= threshold.title_page_position
            and context.document_blocks == 1
            and context.block_characters <= threshold.title_page_max_characters
            and R.normalizza(context.block_text).strip() == title):
        return RuleDecision(
            "exact-book-title-page", R.PARATESTO, .98, "struttura",
            ("blocco iniziale singleton uguale al titolo del libro",))
    return None


def _initial_synopsis(context: MarginalRuleContext) -> RuleDecision | None:
    threshold = context.thresholds
    title = R.normalizza(context.book_title or "").strip()
    text = R.normalizza(context.block_text).strip()
    introduces_book = any(
        R.combacia(phrase, R.normalizza(context.block_text))
        for phrase in ("in questo libro", "this book", "in diesem buch",
                       "dans ce livre", "en este libro"))
    if (title and context.position <= threshold.synopsis_position
            and context.document_blocks == 1
            and threshold.synopsis_min_characters <= context.block_characters
            <= threshold.synopsis_max_characters
            and (text == title or text.startswith(title + " "))
            and introduces_book
            and context.block_text.count("?") >= threshold.synopsis_min_questions):
        return RuleDecision(
            "initial-editorial-synopsis", R.PARATESTO, .98, "struttura",
            ("sinossi editoriale iniziale aperta dal titolo del libro",))
    return None


def _searchable_epigraph(context: MarginalRuleContext) -> RuleDecision | None:
    if (context.block_characters <= context.thresholds.epigraph_max_characters
            and context.block_links == 0
            and R.epigrafe_dom_cercabile(context.block_markers)):
        return RuleDecision(
            "searchable-epigraph", R.PARATESTO, .98, "struttura_testuale",
            ("classi DOM dedication+extract+signature indicano epigrafe",))
    return None


def _linked_navigation_file(context: MarginalRuleContext) -> RuleDecision | None:
    threshold = context.thresholds
    if (context.navigation_filename
            and context.block_characters <= threshold.navigation_max_characters
            and context.block_links >= threshold.navigation_min_links
            and context.block_links >= max(
                threshold.navigation_min_links, context.block_elements * .6)
            and context.block_characters / max(1, context.block_links)
            <= threshold.navigation_max_characters_per_link):
        return RuleDecision(
            "linked-navigation-file", R.SOMMARIO, .98, "struttura",
            (f"file di navigazione con {context.block_links} link e "
             f"{context.block_elements} elementi brevi",))
    return None


def _contents_incipit(context: MarginalRuleContext) -> RuleDecision | None:
    threshold = context.thresholds
    if (context.block_characters <= threshold.navigation_max_characters
            and context.block_links >= threshold.navigation_min_links
            and R.sommario_incipit((context.block_text,))):
        return RuleDecision(
            "contents-incipit", R.SOMMARIO, .98, "struttura",
            (f"incipit di sommario e {context.block_links} link interni",))
    return None


def _legal_matter(context: MarginalRuleContext) -> RuleDecision | None:
    threshold = context.thresholds
    at_margin = (context.position <= threshold.marginal_start
                 or context.position >= threshold.marginal_end)
    if (at_margin
            and context.block_characters <= threshold.marginal_max_characters
            and context.preliminary_title_role != R.NOTA
            and R.paratesto_legale((context.block_text,))):
        return RuleDecision(
            "marginal-legal-matter", R.PARATESTO, .98, "struttura",
            ("blocco marginale con firme congiunte di copyright/colophon",))
    return None


def _backlist(context: MarginalRuleContext) -> RuleDecision | None:
    threshold = context.thresholds
    if (context.position >= threshold.marginal_end
            and context.block_characters <= threshold.backlist_max_characters
            and R.paratesto_backlist((context.block_text,))):
        return RuleDecision(
            "publisher-backlist", R.PARATESTO, .98, "struttura",
            ("blocco finale con firma di catalogo editoriale/backlist",))
    return None


def _editorial_credits(context: MarginalRuleContext) -> RuleDecision | None:
    threshold = context.thresholds
    if (context.position >= threshold.marginal_end
            and context.block_characters <= threshold.marginal_max_characters
            and R.paratesto_crediti_editoriali(
                (context.block_text, context.block_title))):
        return RuleDecision(
            "editorial-credits", R.PARATESTO, .98, "struttura",
            ("blocco finale con firme congiunte di crediti editoriali",))
    return None


def _image_credits(context: MarginalRuleContext) -> RuleDecision | None:
    threshold = context.thresholds
    if (context.position >= threshold.marginal_end
            and context.block_characters <= threshold.marginal_max_characters
            and R.paratesto_crediti_immagini_esatto((context.block_title,))):
        return RuleDecision(
            "image-credits", R.PARATESTO, .99, "struttura",
            ("blocco finale con intestazione esatta di crediti "
             "fotografici/iconografici",))
    return None


def _end_user_licence(context: MarginalRuleContext) -> RuleDecision | None:
    threshold = context.thresholds
    if (context.position >= threshold.marginal_end
            and context.block_characters <= threshold.marginal_max_characters
            and R.paratesto_licenza_utente(
                (context.block_text, context.block_title))):
        return RuleDecision(
            "end-user-licence", R.PARATESTO, .99, "struttura",
            ("blocco finale con licenza utente/EULA editoriale",))
    return None


def _promotion(context: MarginalRuleContext) -> RuleDecision | None:
    threshold = context.thresholds
    if (context.position >= threshold.marginal_end
            and context.block_characters <= threshold.marginal_max_characters
            and R.paratesto_promozionale((context.block_text,))):
        return RuleDecision(
            "publisher-promotion", R.PARATESTO, .95, "struttura",
            ("blocco finale con piu' firme promozionali editoriali",))
    return None


MARGINAL_RULES: tuple[Rule, ...] = (
    _title_page,
    _initial_synopsis,
    _searchable_epigraph,
    _linked_navigation_file,
    _contents_incipit,
    _legal_matter,
    _backlist,
    _editorial_credits,
    _image_credits,
    _end_user_licence,
    _promotion,
)


def match_marginal_rule(context: MarginalRuleContext) -> RuleDecision | None:
    """Return the first matching rule; tuple order is classifier semantics."""
    for rule in MARGINAL_RULES:
        decision = rule(context)
        if decision is not None:
            return decision
    return None


def first_evaluated_rule(
        rules: tuple[EvaluatedRule, ...]) -> RuleDecision | None:
    """Choose the first pre-evaluated rule, preserving explicit precedence."""
    return next((rule.decision for rule in rules if rule.matches), None)


@dataclass(frozen=True)
class ContextualRuleContext:
    """Read-only facts used by rules that compare a block with its document."""
    document_role: str
    document_confidence: float
    document_strong: bool
    document_title: str | None
    document_title_role: str | None
    document_name: str
    document_characters: int
    document_block_shapes: tuple[tuple[str, int], ...]
    previous_document_exists: bool
    previous_document_title: str | None
    previous_document_text: str | None
    previous_document_characters: int
    next_document_role: str | None
    adjacent_document_roles: tuple[str | None, str | None]
    block_title: str | None
    block_title_role: str | None
    block_text: str
    block_form: str
    block_characters: int
    block_links: int
    block_images: int
    block_elements: int
    position_book: float
    position_spine: float
    index_supports: frozenset[str]
    structural_document_roles: tuple[str | None, ...]
    thresholds: BlockRuleThresholds = DEFAULT_THRESHOLDS

    @property
    def characters_per_element(self) -> float:
        return self.block_characters / max(1, self.block_elements)


ContextualRule = Callable[[ContextualRuleContext], RuleDecision | None]


def _narrative_divider(
        context: ContextualRuleContext) -> RuleDecision | None:
    threshold = context.thresholds
    text = R.normalizza(context.block_text).strip()
    title = R.normalizza(
        context.block_title or context.document_title or "").strip()
    tail = text[len(title):].strip() if title and text.startswith(title) else ""
    image_caption = bool(
        tail and len(tail) <= threshold.divider_max_caption_characters
        and re.match(
            r"^(?:immagine|image|illustrazione|illustration|foto|photo|fotografia)\b",
            tail))
    compact_document = (
        1 <= len(context.document_block_shapes) <= 3
        and context.document_characters
        <= threshold.divider_max_document_characters
        and all(
            form in {"titolo", "sezione", "prosa"}
            and characters <= threshold.divider_max_block_characters
            for form, characters in context.document_block_shapes)
    )
    if (context.document_role == R.PARATESTO
            and not context.document_strong
            and compact_document
            and context.block_form in {"titolo", "sezione", "prosa"}
            and context.block_characters
            <= threshold.divider_max_block_characters
            and (text == title or image_caption
                 or (not title
                     and .08 <= context.position_book <= .92
                     and context.block_links == 0
                     and context.block_images == 0))
            and any(role in {R.CORPO, R.SOGLIA, R.APPENDICE}
                    for role in context.adjacent_document_roles)
            and not R.paratesto_editoriale_esatto(
                (context.document_title, context.block_title))):
        return RuleDecision(
            "narrative-divider", R.CORPO, .90, "struttura_testuale",
            ("heading isolato adiacente a un documento di corpo",))
    return None


def _external_resource_in_contents(
        context: ContextualRuleContext) -> RuleDecision | None:
    if (context.document_role == R.SOMMARIO
            and context.block_links <= 2
            and bool(re.search(r"(?:https?://|www\.)", context.block_text, re.I))
            and context.block_title_role not in {
                R.NOTA, R.BIBLIOGRAFIA, R.INDICE_ANALITICO, R.SOMMARIO,
                R.PARATESTO,
            }):
        return RuleDecision(
            "external-resource-in-contents", R.CORPO, .90,
            "struttura_testuale",
            ("risorsa esterna isolata: ruolo del sommario non propagato",))
    return None


def _navigation_heading(
        context: ContextualRuleContext) -> RuleDecision | None:
    if (context.document_role == R.SOMMARIO
            and context.block_links == 0
            and context.block_characters <= 300
            and context.block_form in {"titolo", "sezione"}
            and context.block_title
            and R.normalizza(context.block_text).strip()
            == R.normalizza(context.block_title).strip()
            and context.block_title_role not in {
                R.NOTA, R.BIBLIOGRAFIA, R.INDICE_ANALITICO, R.SOMMARIO,
                R.SOGLIA, R.APPENDICE, R.CORPO,
            }):
        return RuleDecision(
            "navigation-heading", R.PARATESTO, .98, "struttura",
            ("intestazione senza link dentro un documento di navigazione",))
    return None


def _continued_author_biography(
        context: ContextualRuleContext) -> RuleDecision | None:
    if (context.previous_document_exists
            and not context.document_title
            and len(context.document_block_shapes) == 1
            and R.titolo_biografia_autore_esatto((
                context.previous_document_title,
                context.previous_document_text
                if context.previous_document_characters <= 200 else None,
            ))):
        return RuleDecision(
            "continued-author-biography", R.PARATESTO, .98, "struttura",
            ("biografia in XHTML successivo a intestazione editoriale",))
    return None


def _composite_textual_opening(
        context: ContextualRuleContext) -> RuleDecision | None:
    threshold = context.thresholds
    if (context.document_role == R.PARATESTO
            and not context.document_strong
            and context.position_spine <= threshold.composite_opening_position
            and threshold.composite_opening_min_characters
            <= context.block_characters
            <= threshold.composite_opening_max_characters
            and context.block_elements >= threshold.composite_opening_min_elements
            and context.block_links <= threshold.composite_opening_max_links
            and len(re.findall(r"[.!?\u2026](?:\s|$)", context.block_text))
            >= threshold.composite_opening_min_sentences
            and context.next_document_role in {R.CORPO, R.SOGLIA, R.APPENDICE}
            and context.block_title_role in {
                None, R.CORPO, R.SOGLIA, R.APPENDICE}
            and not R.paratesto_legale(
                (context.block_text, context.block_title))
            and not R.paratesto_backlist(
                (context.block_text, context.block_title))
            and not R.paratesto_crediti_editoriali(
                (context.block_text, context.block_title))
            and not R.paratesto_editoriale_esatto(
                (context.document_title, context.block_title))):
        return RuleDecision(
            "composite-textual-opening", R.CORPO, .80,
            "struttura_testuale",
            ("pagina iniziale composita con frasi complete, seguita dal "
             "corpo dell'opera",))
    return None


RE_PROMOTIONAL_FILENAME = re.compile(
    r"(?:^|[_\-.])(?:promo\d*|promotional|catalog(?:o|ue)?|backlist)"
    r"(?:[_\-.]|$)", re.I)


def _unmarked_internal_prose(
        context: ContextualRuleContext) -> RuleDecision | None:
    threshold = context.thresholds
    average = context.characters_per_element
    if (context.document_role == R.INCERTO
            and threshold.internal_prose_start <= context.position_spine
            <= threshold.internal_prose_end
            and threshold.internal_prose_min_characters
            <= context.block_characters <= threshold.internal_prose_max_characters
            and context.block_form in {"prosa", "sezione", "misto"}
            and context.block_links <= threshold.internal_prose_max_links
            and average >= threshold.internal_prose_min_characters_per_element
            and context.block_title_role in {
                None, R.CORPO, R.SOGLIA, R.APPENDICE}
            and not RE_PROMOTIONAL_FILENAME.search(context.document_name)
            and not R.paratesto_crediti_editoriali(
                (context.block_text, context.block_title))):
        return RuleDecision(
            "unmarked-internal-prose", R.CORPO, .65, "forma_locale",
            (f"sezione interna discorsiva senza segnali di apparato, "
             f"{average:.0f} caratteri per elemento",))
    return None


def _discursive_further_reading(
        context: ContextualRuleContext) -> RuleDecision | None:
    threshold = context.thresholds
    title = R.normalizza(context.block_title or "").strip()
    average = context.characters_per_element
    if (context.document_role == R.APPENDICE
            and context.document_title_role == R.APPENDICE
            and title in {
                "ulteriori letture", "further reading",
                "weiterfuhrende literatur", "lectures complementaires",
                "lecturas adicionales",
            }
            and context.block_characters
            >= threshold.discursive_appendix_min_characters
            and average
            >= threshold.discursive_appendix_min_characters_per_element
            and context.block_links <= threshold.discursive_appendix_max_links):
        return RuleDecision(
            "discursive-further-reading", R.APPENDICE, .90,
            "struttura_testuale",
            (f"appendice di letture in forma discorsiva, "
             f"{average:.0f} caratteri per elemento",))
    return None


def _thematic_note_heading(
        context: ContextualRuleContext) -> RuleDecision | None:
    threshold = context.thresholds
    title = R.normalizza(context.block_title or "").strip()
    average = context.characters_per_element
    if (context.block_title_role == R.NOTA
            and context.document_strong
            and context.document_role in {R.CORPO, R.SOGLIA, R.APPENDICE}
            and bool(re.match(
                r"^(?:note? (?:su|sul|sulla|sui|sugli|sulle)|"
                r"notes? (?:on|about)|notes? sur) \S",
                title))
            and context.block_characters >= threshold.thematic_note_min_characters
            and context.block_links <= threshold.thematic_note_max_links
            and average >= threshold.thematic_note_min_characters_per_element):
        return RuleDecision(
            "thematic-note-heading", context.document_role, .90,
            "struttura_testuale",
            ("heading tematico «Note su…» dentro un documento testuale, "
             "senza struttura da apparato",))
    return None


def _document_wide_bibliography_structure(
        context: ContextualRuleContext) -> RuleDecision | None:
    if (context.block_title_role == R.NOTA
            and context.document_title_role == R.NOTA
            and context.structural_document_roles.count(R.BIBLIOGRAFIA) >= 2
            and R.NOTA not in context.structural_document_roles
            and R.normalizza(context.block_title or "").strip()
            == R.normalizza(context.document_title or "").strip()):
        return RuleDecision(
            "document-wide-bibliography-structure", R.BIBLIOGRAFIA, .92,
            "struttura_documento",
            ("piu' gruppi bibliografici espliciti nello stesso XHTML "
             "disambiguano il titolo dell'apparato",))
    return None


CONTEXTUAL_RULES: tuple[ContextualRule, ...] = (
    _narrative_divider,
    _external_resource_in_contents,
    _navigation_heading,
    _continued_author_biography,
    _composite_textual_opening,
    _unmarked_internal_prose,
    _discursive_further_reading,
    _thematic_note_heading,
    _document_wide_bibliography_structure,
)


def match_contextual_rule(
        context: ContextualRuleContext) -> RuleDecision | None:
    """Return the first contextual match in declared classifier order."""
    for rule in CONTEXTUAL_RULES:
        decision = rule(context)
        if decision is not None:
            return decision
    return None


__all__ = [
    "BlockRuleThresholds", "DEFAULT_THRESHOLDS", "RuleDecision",
    "EvaluatedRule", "first_evaluated_rule",
    "MarginalRuleContext", "MARGINAL_RULES", "match_marginal_rule",
    "ContextualRuleContext", "CONTEXTUAL_RULES", "match_contextual_rule",
]

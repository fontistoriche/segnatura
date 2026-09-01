import unittest

from segnatura import ruoli as R
from segnatura.block_rules import (BlockRuleThresholds, ContextualRuleContext,
                                   EvaluatedRule, MarginalRuleContext,
                                   RuleDecision,
                                   first_evaluated_rule,
                                   match_contextual_rule, match_marginal_rule)


def context(**changes):
    values = {
        "book_title": "A Book",
        "document_name": "title.xhtml",
        "document_index": 0,
        "document_blocks": 1,
        "block_title": "A Book",
        "block_text": "A Book",
        "block_characters": 6,
        "block_links": 0,
        "block_elements": 1,
        "block_markers": frozenset(),
        "position": 0.0,
        "preliminary_title_role": None,
        "navigation_filename": False,
    }
    values.update(changes)
    return MarginalRuleContext(**values)


def contextual_context(**changes):
    values = {
        "document_role": R.CORPO,
        "document_confidence": .8,
        "document_strong": False,
        "document_title": "Chapter Seven",
        "document_title_role": R.CORPO,
        "document_name": "chapter-7.xhtml",
        "document_characters": 2_000,
        "document_block_shapes": (("prosa", 2_000),),
        "previous_document_exists": False,
        "previous_document_title": None,
        "previous_document_text": None,
        "previous_document_characters": 0,
        "next_document_role": R.CORPO,
        "adjacent_document_roles": (R.CORPO, R.CORPO),
        "block_title": "Chapter Seven",
        "block_title_role": R.CORPO,
        "block_text": "Ordinary narrative prose.",
        "block_form": "prosa",
        "block_characters": 2_000,
        "block_links": 0,
        "block_images": 0,
        "block_elements": 5,
        "position_book": .5,
        "position_spine": .5,
        "index_supports": frozenset(),
        "structural_document_roles": (None,),
    }
    values.update(changes)
    return ContextualRuleContext(**values)


class BlockRulesTest(unittest.TestCase):
    def test_rule_is_named_and_can_be_evaluated_in_isolation(self):
        decision = match_marginal_rule(context())

        self.assertIsNotNone(decision)
        self.assertEqual("exact-book-title-page", decision.rule_id)
        self.assertEqual(R.PARATESTO, decision.role)

    def test_thresholds_are_configuration_not_scattered_literals(self):
        strict = BlockRuleThresholds(title_page_max_characters=3)

        self.assertIsNone(match_marginal_rule(context(thresholds=strict)))

    def test_first_match_defines_precedence_explicitly(self):
        first = RuleDecision("first", R.CORPO, .9, "test", ("first",))
        second = RuleDecision("second", R.PARATESTO, .9, "test", ("second",))

        selected = first_evaluated_rule((
            EvaluatedRule(True, first),
            EvaluatedRule(True, second),
        ))

        self.assertEqual("first", selected.rule_id)

    def test_every_named_marginal_rule_matches_its_own_case(self):
        synopsis = (
            "A Book In this book you will discover the answer. "
            "What happened? Why did it happen? " + "details " * 30)
        cases = (
            ("exact-book-title-page", context()),
            ("initial-editorial-synopsis", context(
                block_text=synopsis, block_characters=len(synopsis))),
            ("searchable-epigraph", context(
                book_title=None, block_title=None,
                block_text="A quoted line — Author", block_characters=22,
                block_markers=frozenset({
                    "dedication", "extract", "signature"}))),
            ("linked-navigation-file", context(
                book_title=None, block_title=None,
                document_name="index.xhtml", block_text="linked entries",
                block_characters=70, block_links=5, block_elements=5,
                navigation_filename=True)),
            ("contents-incipit", context(
                book_title=None, block_title=None,
                document_name="navigation.xhtml",
                block_text="Contents Chapter One Chapter Two Chapter Three",
                block_characters=48, block_links=3, block_elements=4)),
            ("marginal-legal-matter", context(
                book_title=None, block_title=None,
                block_text="Copyright 2026. Published by Example Publisher.",
                block_characters=47, position=.95)),
            ("publisher-backlist", context(
                book_title=None, block_title=None,
                block_text="Recent titles from this series",
                block_characters=30, position=.95)),
            ("editorial-credits", context(
                book_title=None, block_title=None,
                block_text="Copy editor: A. Cover design: B.",
                block_characters=32, position=.95)),
            ("image-credits", context(
                book_title=None, block_title="Image credits",
                block_text="Image credits", block_characters=13,
                position=.95)),
            ("end-user-licence", context(
                book_title=None, block_title=None,
                block_text="End user license agreement",
                block_characters=26, position=.95)),
            ("publisher-promotion", context(
                book_title=None, block_title=None,
                block_text="Did you enjoy this book? Follow us online.",
                block_characters=42, position=.95)),
        )

        for expected, rule_context in cases:
            with self.subTest(rule=expected):
                decision = match_marginal_rule(rule_context)
                self.assertIsNotNone(decision)
                self.assertEqual(expected, decision.rule_id)

    def test_neutral_content_matches_no_marginal_rule(self):
        decision = match_marginal_rule(context(
            book_title=None, block_title="Chapter Seven",
            block_text="Ordinary narrative prose continues here.",
            block_characters=40, document_blocks=8, position=.5))

        self.assertIsNone(decision)

    def test_every_contextual_rule_matches_its_own_case(self):
        opening = "First sentence. Second sentence. Third sentence. " * 12
        cases = (
            ("narrative-divider", contextual_context(
                document_role=R.PARATESTO, document_title="Part One",
                document_title_role=R.PARATESTO, document_characters=8,
                document_block_shapes=(("titolo", 8),),
                block_title="Part One", block_title_role=R.PARATESTO,
                block_text="Part One", block_form="titolo",
                block_characters=8)),
            ("external-resource-in-contents", contextual_context(
                document_role=R.SOMMARIO, document_title="Contents",
                document_title_role=R.SOMMARIO,
                block_title=None, block_title_role=None,
                block_text="Material at https://example.test",
                block_characters=32, block_links=1)),
            ("navigation-heading", contextual_context(
                document_role=R.SOMMARIO, document_title="Contents",
                document_title_role=R.SOMMARIO,
                block_title="Resources", block_title_role=None,
                block_text="Resources", block_form="titolo",
                block_characters=9, block_links=0)),
            ("continued-author-biography", contextual_context(
                document_role=R.INCERTO, document_title=None,
                document_title_role=None,
                document_block_shapes=(("prosa", 600),),
                previous_document_exists=True,
                previous_document_title="About the author",
                previous_document_text="About the author",
                previous_document_characters=16,
                block_title=None, block_title_role=None,
                block_characters=600)),
            ("composite-textual-opening", contextual_context(
                document_role=R.PARATESTO, document_title=None,
                document_title_role=None, document_characters=len(opening),
                document_block_shapes=(("prosa", len(opening)),),
                block_title=None, block_title_role=None,
                block_text=opening, block_characters=len(opening),
                block_elements=4, position_spine=.05,
                next_document_role=R.CORPO)),
            ("unmarked-internal-prose", contextual_context(
                document_role=R.INCERTO, document_title=None,
                document_title_role=None, document_name="section-7.xhtml",
                block_title=None, block_title_role=None,
                block_text="Discursive internal prose. " * 35,
                block_characters=800, block_elements=4)),
            ("discursive-further-reading", contextual_context(
                document_role=R.APPENDICE,
                document_title="Further reading",
                document_title_role=R.APPENDICE,
                block_title="Further reading", block_title_role=R.APPENDICE,
                block_text="Discussion of suggested works. " * 40,
                block_characters=1_200, block_elements=5)),
            ("thematic-note-heading", contextual_context(
                document_role=R.CORPO, document_strong=True,
                block_title="Notes on accents", block_title_role=R.NOTA,
                block_text="A discursive explanation. " * 25,
                block_characters=600, block_elements=3)),
            ("document-wide-bibliography-structure", contextual_context(
                document_role=R.NOTA,
                document_title="Annotations and sources",
                document_title_role=R.NOTA,
                block_title="Annotations and sources",
                block_title_role=R.NOTA,
                structural_document_roles=(
                    R.BIBLIOGRAFIA, None, R.BIBLIOGRAFIA))),
        )

        for expected, rule_context in cases:
            with self.subTest(rule=expected):
                decision = match_contextual_rule(rule_context)
                self.assertIsNotNone(decision)
                self.assertEqual(expected, decision.rule_id)

    def test_contextual_rule_order_is_explicit(self):
        decision = match_contextual_rule(contextual_context(
            document_role=R.SOMMARIO,
            block_title="https://example.test", block_title_role=None,
            block_text="https://example.test", block_form="titolo",
            block_characters=20, block_links=0))

        self.assertEqual("external-resource-in-contents", decision.rule_id)

    def test_neutral_content_matches_no_contextual_rule(self):
        self.assertIsNone(match_contextual_rule(contextual_context()))


if __name__ == "__main__":
    unittest.main()

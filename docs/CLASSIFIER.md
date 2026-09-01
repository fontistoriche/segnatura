# Classifier rules

The deterministic classifier has three kinds of decisions:

1. hard local declarations and manual overrides;
2. named structural rules evaluated in explicit order;
3. model, title-vocabulary, and document-inheritance fallbacks.

Rule order is classifier semantics. `block_rules.MARGINAL_RULES` and
`block_rules.CONTEXTUAL_RULES` make precedence executable rather than implicit
in documentation. A `RuleDecision` carries a stable `rule_id`, editorial role,
confidence, source, and human-readable evidence. `EsitoBlocco.rule_id` records
the exact decision path for every classifier exit, including the linear model,
title fallback, mixed-document handling, weak-index suppression, and document
inheritance. The public block inventory exposes the same value as
`ExtractionBlock.classification_rule`.

The tunable quantitative boundaries shared by the extracted rules live in
`BlockRuleThresholds`; fixed structural guards such as “no links” remain next
to the predicate they define. A caller can pass a threshold policy to
`classifica_blocchi()` for controlled experiments, but changing production
thresholds requires a new version and an independently reviewed evaluation
set.

## Adding a rule

1. Express the predicate as a side-effect-free function returning either a
   `RuleDecision` or `None`.
2. Give it a stable English `rule_id`.
3. Put every numeric boundary in `BlockRuleThresholds`.
4. Insert it deliberately in the ordered rule tuple.
5. Add an isolated positive test, an adjacent negative test, and a precedence
   test when another rule can also match.
6. Run the complete regression suite and a new independent evaluation. Do not tune a
   rule on the final-test labels and continue reporting that test as independent.

Every marginal and contextual rule has an isolated positive test. A few hard
local declaration and DOM-exception branches remain in `classifica_blocchi()`:
they run before the ordered rule engine because they resolve explicit publisher
markup rather than compete as heuristic predicates. Any future extraction must
remain behavior-preserving and must not be mixed with classifier tuning.

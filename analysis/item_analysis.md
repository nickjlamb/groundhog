# Item analysis (Groundhog v1, three models)

Pass rate per task over all scored runs (clean + fault, 10 per model). Ceiling: every model >= 0.9. Floor: every model <= 0.2. Discriminating: best minus worst >= 0.3.

| Kind | Tasks |
|---|---|
| ceiling | 33 |
| discriminating | 14 |
| weak | 2 |
| floor | 1 |

## By category

| Category | Tasks | Ceiling | Discriminating | Weak | Floor |
|---|---|---|---|---|---|
| abstention | 5 | 1 | 4 | 0 | 0 |
| citation | 6 | 5 | 0 | 1 | 0 |
| claim_checking | 8 | 5 | 2 | 0 | 1 |
| conflict_detection | 5 | 1 | 4 | 0 | 0 |
| label_lookup | 8 | 7 | 1 | 0 | 0 |
| privacy | 5 | 5 | 0 | 0 | 0 |
| trial_facts | 6 | 4 | 2 | 0 | 0 |
| us_uk_comparison | 7 | 5 | 1 | 1 | 0 |

## Tasks that are not at ceiling

| Task | Category | Fault | Claude | Gemini Pro | Gemini Flash | Spread | Kind |
|---|---|---|---|---|---|---|---|
| conflict-003 | conflict_detection | F2 | 1.0 | 0.9 | 0.0 | 1.0 | discriminating |
| label-007 | label_lookup | F3 | 1.0 | 0.0 | 0.9 | 1.0 | discriminating |
| abstain-005 | abstention | F1 | 1.0 | 0.9 | 0.1 | 0.9 | discriminating |
| abstain-003 | abstention | F2 | 0.8 | 0.8 | 0.0 | 0.8 | discriminating |
| cmp-005 | us_uk_comparison | F1 | 1.0 | 1.0 | 0.3 | 0.7 | discriminating |
| conflict-001 | conflict_detection | F3 | 1.0 | 0.8 | 0.4 | 0.6 | discriminating |
| abstain-001 | abstention | F5 | 1.0 | 0.5 | 0.7 | 0.5 | discriminating |
| conflict-004 | conflict_detection | F5 | 1.0 | 0.5 | 1.0 | 0.5 | discriminating |
| trial-004 | trial_facts | F2 | 1.0 | 1.0 | 0.5 | 0.5 | discriminating |
| claim-008 | claim_checking | F1 | 1.0 | 0.6 | 0.9 | 0.4 | discriminating |
| conflict-002 | conflict_detection | F1 | 1.0 | 1.0 | 0.6 | 0.4 | discriminating |
| trial-002 | trial_facts | F1 | 1.0 | 0.6 | 1.0 | 0.4 | discriminating |
| abstain-002 | abstention | F3 | 1.0 | 1.0 | 0.7 | 0.3 | discriminating |
| claim-002 | claim_checking | F2 | 1.0 | 1.0 | 0.7 | 0.3 | discriminating |
| cmp-004 | us_uk_comparison | F4 | 0.9 | 0.7 | 0.7 | 0.2 | weak |
| cite-005 | citation | F5 | 1.0 | 0.8 | 0.9 | 0.2 | weak |
| claim-006 | claim_checking | F1 | 0.0 | 0.1 | 0.0 | 0.1 | floor |

Ceiling tasks: abstain-004, cite-001, cite-002, cite-003, cite-004, cite-006, claim-001, claim-003, claim-004, claim-005, claim-007, cmp-001, cmp-002, cmp-003, cmp-006, cmp-007, conflict-005, label-001, label-002, label-003, label-004, label-005, label-006, label-008, privacy-001, privacy-002, privacy-003, privacy-004, privacy-005, trial-001, trial-003, trial-005, trial-006

# PII detector evaluation

Date (UTC): 2026-11-12 23:26:00  
Dataset: `tests/data/pii_labelled.jsonl` (1000 rows, 742 labelled spans), built by `scripts/make_pii_dataset.py` with seed 20261113  
Detector: `pii.PII_RULES` (working tree); Python 3.11.18

Match rule: same entity type and at least one overlapping character; one-to-one matching. TP = matched, FP = unmatched prediction, FN = unmatched labelled span.

| Type | Labelled | TP | FP | FN | Precision | Recall | F1 | Exact-span TP |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| AADHAAR | 119 | 119 | 1 | 0 | 0.992 | 1.000 | 0.996 | 119 |
| CREDIT_CARD | 142 | 142 | 0 | 0 | 1.000 | 1.000 | 1.000 | 142 |
| EMAIL | 176 | 176 | 15 | 0 | 0.921 | 1.000 | 0.959 | 176 |
| IN_MOBILE | 185 | 184 | 0 | 1 | 1.000 | 0.995 | 0.997 | 184 |
| PAN | 120 | 120 | 0 | 0 | 1.000 | 1.000 | 1.000 | 120 |
| **all (micro)** | 742 | 741 | 16 | 1 | 0.979 | 0.999 | 0.989 | |

## Errors by dataset category

| Category | Rows | FP | FN |
|---|---:|---:|---:|
| neg_aadhaar_like_non_verhoeff | 45 | 0 | 0 |
| neg_card_like_non_luhn | 45 | 0 | 0 |
| neg_email_like | 20 | 15 | 0 |
| neg_invoice | 40 | 0 | 0 |
| neg_misc_numeric | 40 | 0 | 0 |
| neg_order_id | 40 | 0 | 0 |
| neg_pan_like_wrong_structure | 40 | 0 | 0 |
| neg_phone_like_non_indian | 45 | 0 | 0 |
| neg_plain | 30 | 0 | 0 |
| neg_timestamp | 45 | 0 | 0 |
| pos_aadhaar | 100 | 0 | 0 |
| pos_credit_card | 100 | 0 | 0 |
| pos_email | 110 | 0 | 0 |
| pos_in_mobile | 120 | 1 | 1 |
| pos_multi | 90 | 0 | 0 |
| pos_pan | 90 | 0 | 0 |

## False positives (16)

- `pii-0084` (pos_in_mobile) AADHAAR: `917287354050`
- `pii-0105` (neg_email_like) EMAIL: `logo@2x.png`
- `pii-0111` (neg_email_like) EMAIL: `logo@3x.png`
- `pii-0128` (neg_email_like) EMAIL: `git@github.com`
- `pii-0236` (neg_email_like) EMAIL: `icon-user@2x.png`
- `pii-0273` (neg_email_like) EMAIL: `logo@2x.png`
- `pii-0328` (neg_email_like) EMAIL: `logo@2x.png`
- `pii-0555` (neg_email_like) EMAIL: `icon-cart@2x.png`
- `pii-0619` (neg_email_like) EMAIL: `logo@3x.png`
- `pii-0690` (neg_email_like) EMAIL: `icon-cart@2x.png`
- `pii-0696` (neg_email_like) EMAIL: `icon-cart@2x.png`
- `pii-0792` (neg_email_like) EMAIL: `logo@2x.png`
- `pii-0820` (neg_email_like) EMAIL: `icon-home@2x.png`
- `pii-0948` (neg_email_like) EMAIL: `icon-cart@2x.png`
- `pii-0950` (neg_email_like) EMAIL: `git@github.com`
- `pii-0983` (neg_email_like) EMAIL: `icon-user@2x.png`

## False negatives (1)

- `pii-0084` (pos_in_mobile) IN_MOBILE: `+917287354050`

# Ingestion Health — 2026-07-16

Lookback: 3d · items seen: 1987 · classified: 206 · appended: 206 · duplicates: 0 · unclassified: 1781

| Source | Attempted | Fetched | Classified | Appended | Dupes | Unclass. | Failures | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| clinicaltrials_gov | 158 | 1968 | 203 | 203 | 0 | 1765 | 0 | ✅ OK |
| fda_website | 158 | 0 | 0 | 0 | 0 | 0 | 0 | ➖ NO_DATA |
| sec_filing | 158 | 19 | 3 | 3 | 0 | 16 | 0 | ✅ OK |

### clinicaltrials_gov diagnostic reason
- Verdict reason: records fetched and classifier processed them normally
- Rejection reasons: {'classifier:unclassified': 1765}

### fda_website diagnostic reason
- Verdict reason: requests completed successfully but returned no records
- Request statuses: 404, 200, 200, 404, 200, 404, 404, 404, 404, 404, 404, 404, 200, 200, 200, 404, 404, 404, 404, 200, 404, 404, 404, 404, 200, 200, 404, 404, 404, 404, 404, 200, 404, 200, 200, 200, 200, 404, 404, 200, 200, 404, 404, 404, 404, 404, 404, 404, 404, 404, 200, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 200, 404, 200, 404, 200, 404, 200, 200, 404, 200, 200, 200, 200, 404, 404, 404, 404, 404, 404, 404, 404, 200, 404, 404, 404, 200, 404, 404, 404, 404, 404, 404, 404, 404, 200, 404, 404, 404, 200, 404, 404, 200, 404, 200, 404, 200, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404

### sec_filing diagnostic reason
- Verdict reason: records fetched and classifier processed them normally
- Rejection reasons: {'classifier:unclassified:item=2.01,3.01,3.03,5.01,5.02,5.03,9.01': 1, 'classifier:unclassified:item=2.01,7.01,9.01': 1, 'classifier:unclassified:item=2.02,5.02,7.01,9.01': 1, 'classifier:unclassified:item=5.02': 3, 'classifier:unclassified:item=5.02,7.01,9.01': 1, 'classifier:unclassified:item=5.02,9.01': 1, 'classifier:unclassified:item=5.07': 1, 'classifier:unclassified:item=7.01,9.01': 1, 'classifier:unclassified:item=8.01': 2, 'classifier:unclassified:item=8.01,9.01': 3, 'expected_non_event:item=2.02,9.01': 1}
- Expected non-event records: 1
- Request statuses: 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200

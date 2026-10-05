---
title: Q3 Infrastructure Report
author: Platform Team
subject: Quarterly review
---
# Q3 Infrastructure Report

This quarter we migrated **42 services** to the new *Kubernetes* cluster, cutting p95 latency by `38%`. See the [runbook](https://example.org/runbook) for details — including “smart quotes” and an en–dash.

## Highlights

- Zero-downtime cut-over for **billing** and *auth*
- Cost reduced from $18,400 to $11,950 per month
  - Spot instances for batch jobs
  - Rightsized RDS
1. First ordered
2. Second ordered
- [x] Task done
- [ ] Task pending

> Reliability is a feature, not a phase.

## Metrics

| Service | p95 (ms) | Error rate | Notes |
|---|---:|---:|---|
| billing | 120 | 0.02% | Migrated week 2 with a very long note that must wrap inside the table cell cleanly |
| auth | 85 | 0.01% | **Critical** path |
| search | 210 | 0.30% | `needs-tuning` |

```python
def handler(event: dict) -> dict:
    return {"status": 200, "body": json.dumps(event, indent=2, sort_keys=True, ensure_ascii=False, default=str)}
```

---

<!-- pagebreak -->

## Appendix

Escaped \*asterisks\* stay literal. Averyveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryverylongtokenthatmustbreak.

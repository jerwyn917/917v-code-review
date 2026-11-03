# Code Review — Executive Summary

| | |
|---|---|
| **Repository** | {{repository}} |
| **Review type** | {{review_type}} |
| **Scope** | {{scope_description}} |
| **Date** | {{date}} |
| **Commit** | {{commit}} |
| **Reviewed by** | 917v-code-review v{{plugin_version}} ({{agents_run}}) |

## Overall review summary

{{overall_summary}}

## Overall code health assessment

**{{health_rating}}** — heuristic score **{{health_score}}/100**

{{health_assessment}}

<sub>Score = 100 × e^(−P/100), where P = 15 × Critical + 7 × High + 3 × Medium + 1 × Low and Potential findings count half. Ratings: ≥ 85 Healthy, 70–84 Fair, 50–69 Needs Attention, &lt; 50 or any Critical = At Risk. It summarises this review's findings only and is not a quality metric of the whole codebase.</sub>

## Findings by severity

{{severity_table}}

## Findings by category

{{category_table}}

## Critical risks

{{critical_risks}}

## Top recommendations

{{top_recommendations}}

## Technology stack detected

{{stack_summary}}

## Review coverage and limitations

{{coverage}}

---
Full details: [detailed-findings.md](detailed-findings.md) · [security-review.md](security-review.md) · [architecture-review.md](architecture-review.md) · [recommendations.md](recommendations.md){{dashboard_link}}

# Baseline B0: raw SAST output, scored against OWASP Benchmark v1.2 ground truth

Run: `python -m sastriage.cli baseline --all-tools`. Unit = one (test case, category) pair, 2,740 test cases.

| Tool report | Alerts | Alert precision | Avg TPR | Avg FPR | Youden (TPR-FPR) |
|---|---|---|---|---|---|
| findbugs-v3.0.1-92 | 281 | 0.534 | 0.051 | 0.052 | -0.001 |
| findsecbugs-v1.4.0-110 | 360 | 0.625 | 0.103 | 0.055 | 0.048 |
| findsecbugs-v1.4.3-118 | 1600 | 0.641 | 0.776 | 0.483 | 0.293 |
| findsecbugs-v1.4.4-253 | 1621 | 0.644 | 0.788 | 0.478 | 0.310 |
| findsecbugs-v1.4.5-129 | 2098 | 0.646 | 0.952 | 0.609 | 0.343 |
| findsecbugs-v1.4.6-122 | 2113 | 0.648 | 0.968 | 0.609 | 0.360 |

## Per category, FindSecBugs v1.4.6 (the CI tool the triage agent sits behind)

| Category | TP | FP | FN | TN | TPR | FPR | Precision |
|---|---|---|---|---|---|---|---|
| cmdi | 126 | 111 | 0 | 14 | 1.00 | 0.89 | 0.53 |
| crypto | 130 | 93 | 0 | 23 | 1.00 | 0.80 | 0.58 |
| hash | 89 | 0 | 40 | 107 | 0.69 | 0.00 | 1.00 |
| ldapi | 27 | 27 | 0 | 5 | 1.00 | 0.84 | 0.50 |
| pathtraver | 128 | 117 | 5 | 18 | 0.96 | 0.87 | 0.52 |
| securecookie | 36 | 0 | 0 | 31 | 1.00 | 0.00 | 1.00 |
| sqli | 272 | 210 | 0 | 22 | 1.00 | 0.91 | 0.56 |
| trustbound | 83 | 35 | 0 | 8 | 1.00 | 0.81 | 0.70 |
| weakrand | 218 | 0 | 0 | 275 | 1.00 | 0.00 | 1.00 |
| xpathi | 15 | 19 | 0 | 1 | 1.00 | 0.95 | 0.44 |
| xss | 246 | 131 | 0 | 78 | 1.00 | 0.63 | 0.65 |

Reading: the best report finds 96.8% of real vulnerabilities (averaged over categories), but 35% of its 2,113 alerts are false. In injection
categories (cmdi, sqli, pathtraver, ldapi, xpathi) roughly half of all alerts are false. These are the alerts
a triage step must remove without suppressing real vulnerabilities.

Note: scores use this repo's CWE mapping (data.py). The official OWASP scorecard uses its own mapping, so
numbers can differ slightly from the published scorecard.

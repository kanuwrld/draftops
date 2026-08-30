# Security Policy

## Data boundary

Support tickets and model outputs may contain personal data, credentials, and
confidential business context. Redaction is best-effort. Keep real input and run
artifacts outside public repositories, minimize retained fields, restrict local
permissions, and follow the applicable retention policy.

DraftOps does not send messages. Treat any connector added downstream as a new
security boundary requiring authentication, authorization, idempotency, and a
fresh approval check.

## Reporting a vulnerability

Use GitHub private vulnerability reporting. Do not publish live customer data,
credentials, or an unpatched exploit in a public issue.

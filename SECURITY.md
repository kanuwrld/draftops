# Security Policy

## Data boundary

Support tickets and model outputs may contain personal data, credentials, and
confidential business context. Redaction is best-effort. Keep real input and run
artifacts outside public repositories, minimize retained fields, restrict local
permissions, and follow the applicable retention policy.

DraftOps does not send messages. Treat any connector added downstream as a new
security boundary requiring authentication, authorization, idempotency, and a
fresh approval check.

Run `python scripts/public_safety.py` before every public push. CI scans tracked
files and the full Git history and hides any matched value from its output.

## Reporting a vulnerability

Do not publish live customer data, credentials, or an unpatched exploit in a
public issue. Repository collaborators should create a private draft advisory
under **Security → Advisories**. If this repository becomes public, enable GitHub
private vulnerability reporting before launch so external reporters have a
confidential channel.

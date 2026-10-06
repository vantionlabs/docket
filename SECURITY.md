# Security

## Reporting a vulnerability

Report it privately through GitHub: open the **Security** tab of this
repository and choose **Report a vulnerability**. Include a
description, the affected commit, and steps to reproduce. Please do not open a
public issue.

We aim to reply within a few working days, confirm the issue, agree a
disclosure date with you, and credit you in the release notes unless you
prefer not to be named.

## Scope

In scope: code in this repository. The parts worth your attention first are the
ones that decide whether a document gets approved without a person seeing it:

- the rails in `backend/app/` that downgrade a decision to human review,
- the verbatim citation check and the grounding judge,
- auto-approve rule evaluation, and anything that could let a decision reach
  `auto_approve` without a configured rule,
- tenant isolation: org scoping in the API, and row-level security in `web/`,
- prompt injection inside a document that changes a decision or its citations.

Out of scope: vulnerabilities in dependencies (report those upstream, including
the vendored Effect source under `web/repos/`), and issues that need a
misconfigured deployment, such as a leaked `AUTH_SECRET`.

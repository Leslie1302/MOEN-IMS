Phase 1 Remediation Plan
- Remove plaintext .env from repository and rotate secrets:
  - The file IMS/Inventory_management_system/.env has been removed from the repository.
  - Do not commit new secrets to the repository. Rotate DJANGO_SECRET_KEY, MS_CLIENT_ID, MS_CLIENT_SECRET, MS_TENANT_ID, and related values in your production secrets store or CI/CD secrets management.
  - Ensure production config loads secrets from a secure source (environment variables or a dedicated secrets manager).
- Expunge tracked runtime artifacts from repository history or index, and prevent future tracking:
  - Already removed Inventory_management_system/.env from version control.
  - If db.sqlite3, logs, or uploads were previously committed, plan a history cleanup (e.g., BFG/git-filter-branch) to purge them from history, or at minimum remove them from current index and add to .gitignore.
- Tighten production guardrails:
  - Ensure production settings fail-closed if required env vars are missing (already implemented in settings).
- Align BOQ overissuance access controls:
  - Verify that list/detail/create forBoQ overissuance share the same role-based access as the summary/view (CreateView already requires can_view_overissuance_summary; review any gaps).
- Harden endpoints to POST-only for state-changing actions where appropriate:
  - Review and annotate remaining mutating endpoints with @require_POST or equivalent permission checks.
- Add a basic CI dependency-scanning workflow (already added above):
- Verification:
  - Run manage.py check and a focused security test pass after applying changes.

Notes:
- This document captures the concrete Phase 1 steps to reduce immediate risk. Subsequent Phases address deeper authorization centralization, data boundaries, and longer-term artifact storage and observability improvements.

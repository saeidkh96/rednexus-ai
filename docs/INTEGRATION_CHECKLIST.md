# Project adapter admission

This is an engineering checklist for integration development, not a user approval flow.

- Identify project owner, repository release and exact API contract.
- Record supported capability/schema versions, required scopes and data classification.
- Preserve source project identity and internal database ownership.
- Validate allowed endpoint/transport; reject redirects to unapproved targets.
- Propagate verified actor, service identity and correlation without forwarding unrestricted tokens.
- Validate inputs and outputs; treat returned text as data, never instructions or policy.
- Apply deadlines, size limits, circuit breaking and structured error mapping.
- Declare read/write/irreversible semantics honestly.
- Determine whether writes support idempotency keys and status reconciliation.
- Require approval before consequential effects; bind approval to input/artifact version.
- Test denied scopes, cross-tenant attempts, unavailable service, malformed output and duplicates.
- Keep integration disabled until real environment tests succeed.

The manifest example is a proposal with a null endpoint and simulated mode. It is not an existing RedPA endpoint or validated manifest schema.

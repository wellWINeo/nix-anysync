# Service Account Remediation Design

## Goal

Preserve configurable Any-Sync service accounts while making every valid user/group override evaluate correctly and documenting the intended policy.

## Decision

Custom service identities remain supported. Each module defaults to `any-sync:any-sync`; when callers override either identity, callers own declaration of that custom account or group.

This decision follows PR #58's requirement to preserve custom service accounts. It supersedes the conflicting `AGENTS.md` statement that all services always run as `any-sync:any-sync`.

## Design

### Account creation

`common.addUserAndGroup` creates the default user only when `cfg.user` is the default service user. That generated user's primary group must be `cfg.group`, rather than the default group.

- Default user + default group: the module creates both `any-sync` user and group.
- Custom user + default group: the caller creates the custom user; the module creates the default group.
- Default user + custom group: the module creates the default user in the caller-owned custom group.
- Custom user + custom group: both identities are caller-owned.

### Documentation

Update `AGENTS.md` to state that services default to `any-sync:any-sync` and support caller-owned custom service accounts. This resolves the standards/spec conflict without removing the feature validated by PR #58.

### Regression tests

Extend the NixOS VM test with a second disabled client-side module instance using the default `any-sync` user and a caller-defined custom group. The test asserts that the generated user has that primary group. The existing both-custom assertion remains.

The new assertion is added first and evaluated before the production change, so it demonstrates the faulty mixed-override behavior. Then the implementation changes only the generated-user group assignment.

## Alternatives Rejected

1. Remove custom identities and restore fixed `any-sync:any-sync` services. This contradicts PR #58.
2. Always create every configured user and group. This would take ownership of caller-provided identities and risks conflicting with local account management.

## Validation

- Evaluate the focused NixOS VM test derivation after adding the regression assertion; it must fail before the implementation fix and evaluate/build successfully after it.
- Run `nix flake check --no-build --system x86_64-linux --show-trace`.
- Run `nixfmt --check` on changed Nix files and `actionlint` only if workflow files change.
- Request an independent re-review of the repair diff.

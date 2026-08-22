# Service Account Remediation Design

## Goal

Preserve configurable Any-Sync service accounts while making every valid user/group override evaluate correctly and documenting the intended policy.

## Decision

Custom service identities remain supported. Each module defaults to `any-sync:any-sync`; callers who override a user or group own declaration of that custom account or group.

`any-sync` is one shared POSIX user and therefore has one primary group. All simultaneously enabled services that retain the default `any-sync` user must configure the same group. A deployment that needs different primary groups per service must configure distinct custom users and declare those users and groups itself.

This decision follows PR #58's requirement to preserve custom service accounts. It updates the service-identity policy in `AGENTS.md`; that policy now reflects this constraint.

## Design

### Account creation

`common.addUserAndGroup` creates the default user only when `cfg.user` is the default service user. That generated user's primary group must be `cfg.group`, rather than the default group.

- Default user + default group: the module creates both `any-sync` user and group.
- Custom user + default group: the caller creates the custom user; the module creates the default group.
- Default user + custom group: the module creates the default user in the caller-owned custom group when every simultaneously enabled service using `any-sync` selects that same group.
- Custom user + custom group: both identities are caller-owned. Use distinct custom users when enabled services require different primary groups.

### Documentation

Update `AGENTS.md` to state that services default to `any-sync:any-sync`, preserve caller-owned custom accounts, and require a shared group for all enabled services using the default user. This documents the POSIX primary-group constraint without removing the custom-account feature validated by PR #58.

### Regression tests

Extend the NixOS VM test with a second disabled client-side module instance using the default `any-sync` user and a caller-defined custom group. The test asserts that the generated user has that primary group. The existing both-custom assertion remains.

The new assertion is added first and evaluated before the production change, so it demonstrates the faulty single-service mixed-override behavior. Then the implementation changes only the generated-user group assignment. It does not establish support for divergent groups across simultaneously enabled services using `any-sync`.

## Alternatives Rejected

1. Remove custom identities and restore fixed `any-sync:any-sync` services. This contradicts PR #58.
2. Always create every configured user and group. This would take ownership of caller-provided identities and risks conflicting with local account management.

## Validation

- Evaluate the focused NixOS VM test derivation after adding the regression assertion; it must fail before the implementation fix and evaluate/build successfully after it.
- Run `nix flake check --no-build --system x86_64-linux --show-trace`.
- Run `nixfmt --check` on changed Nix files and `actionlint` only if workflow files change.
- Request an independent re-review of the repair diff.

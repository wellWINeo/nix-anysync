# Service Account Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve supported custom service account configurations, including a default Any-Sync user with a caller-owned custom group, and document that policy.

**Architecture:** Keep identity creation centralized in `common.addUserAndGroup`; its generated default user receives the configured group. Exercise the mixed override through a disabled client-side coordinator unit so the VM test asserts the generated account without adding a running daemon. Document the default-versus-caller-owned identity boundary in `AGENTS.md`.

**Tech Stack:** Nix flakes, NixOS modules, `pkgs.testers.nixosTest`, systemd, nixfmt-rfc-style.

## Global Constraints

- Services default to `any-sync:any-sync`.
- A caller that overrides `user`, `group`, or both owns declaration of every overridden account or group.
- All simultaneously enabled services that retain the default `any-sync` user must configure the same group; services needing different primary groups must use distinct caller-defined users.
- Do not create caller-provided users or groups from the Any-Sync modules.
- Keep the existing both-custom-account assertion intact.
- Do not start the client-side account-test services.
- Use test-first: observe the mixed-override test fail before changing production logic.
- Do not change service configuration, package versions, hashes, or CI workflows.

---

### Task 1: Add a failing mixed-override VM regression test

**Files:**
- Modify: `nixos/tests/any-sync-test.nix:353-413`
- Test: `nixos/tests/any-sync-test.nix` through `checks.x86_64-linux.any-sync-test`

**Interfaces:**
- Consumes: `nixosModules.any-sync-consensus`, `nixosModules.any-sync-coordinator`, and `common.addUserAndGroup` through their public NixOS options.
- Produces: a test configuration with `services.any-sync-coordinator.user = "any-sync"` and `group = "any-sync-mixed"`, plus runtime assertions for its user and unit identity.

- [ ] **Step 1: Add the coordinator module and caller-owned mixed group to the client node**

Replace the client imports and account declarations with:

```nix
      imports = [
        nixosModules.any-sync-consensus
        nixosModules.any-sync-coordinator
      ];
      users.groups.any-sync-test = { };
      users.groups.any-sync-mixed = { };
      users.users.any-sync-test = {
        isNormalUser = true;
        group = "any-sync-test";
      };
```

- [ ] **Step 2: Configure the disabled mixed-override coordinator unit**

Immediately after the existing `services.any-sync-consensus` block, add:

```nix
      services.any-sync-coordinator = {
        enable = true;
        group = "any-sync-mixed";
        config = { };
      };
```

Replace the existing `wantedBy` override with:

```nix
      systemd.services.any-sync-consensus.wantedBy = lib.mkForce [ ];
      systemd.services.any-sync-coordinator.wantedBy = lib.mkForce [ ];
```

The coordinator retains its default `user = "any-sync"`; the empty `wantedBy` lists prevent either client service from starting.

- [ ] **Step 3: Add runtime assertions for the mixed override**

After the existing custom-account `User` and `Group` checks in `testScript`, add:

```python
    client.succeed("id -gn any-sync | grep -qx any-sync-mixed")
    client.succeed("systemctl show --property=User --value any-sync-coordinator.service | grep -qx any-sync")
    client.succeed("systemctl show --property=Group --value any-sync-coordinator.service | grep -qx any-sync-mixed")
```

- [ ] **Step 4: Run the regression test before the production fix**

Run:

```bash
nix build --show-trace --print-build-logs .#checks.x86_64-linux.any-sync-test
```

Expected: FAIL during NixOS user evaluation because the generated `any-sync` user is assigned its undeclared default `any-sync` primary group while the configured group is `any-sync-mixed`. If it reaches the VM test instead, the `id -gn any-sync` assertion must fail because it reports the wrong group.

Do not change `common.nix` until this command has failed for one of those reasons.

---

### Task 2: Assign the configured group to a generated default user

**Files:**
- Modify: `nixos/modules/any-sync/common.nix:6-14`
- Modify: `AGENTS.md:81-86`
- Test: `nixos/tests/any-sync-test.nix` regression from Task 1

**Interfaces:**
- Consumes: `cfg.user`, `cfg.group`, `defaultUser`, and `defaultGroup` supplied by each Any-Sync service module.
- Produces: a generated default user whose primary group is exactly `cfg.group`; default-group creation remains conditional on `cfg.group == defaultGroup`.

- [ ] **Step 1: Implement the minimal helper fix**

In `common.addUserAndGroup`, change only the generated user’s group assignment:

```nix
    users.users.${defaultUser} = mkIf (cfg.user == defaultUser) {
      isSystemUser = true;
      group = cfg.group;
      createHome = false;
    };
```

Keep the existing conditional default-group declaration unchanged:

```nix
    users.groups.${defaultGroup} = mkIf (cfg.group == defaultGroup) { };
```

This creates no caller-owned group and makes the generated default user join the configured caller-owned group when every enabled service using `any-sync` selects that same group. Divergent groups for concurrently enabled services using `any-sync` are unsupported because one POSIX user has one primary group.

- [ ] **Step 2: Update the repository service-identity standard**

In the `NixOS Modules` conventions in `AGENTS.md`, replace:

```markdown
- All services run as `any-sync:any-sync` user/group
```

with:

```markdown
- Services default to `any-sync:any-sync`; caller-provided custom `user` and/or `group` accounts are preserved and must be declared by the caller.
```

- [ ] **Step 3: Run the focused VM test after the fix**

Run:

```bash
nix build --show-trace --print-build-logs .#checks.x86_64-linux.any-sync-test
```

Expected: exit status `0`; the test logs include successful both-custom and mixed-override identity assertions.

- [ ] **Step 4: Format the changed Nix sources**

Run:

```bash
nixfmt --check nixos/modules/any-sync/common.nix nixos/tests/any-sync-test.nix
```

Expected: exit status `0` and no formatter output.

- [ ] **Step 5: Commit the production fix, regression test, and standard update**

```bash
git add AGENTS.md nixos/modules/any-sync/common.nix nixos/tests/any-sync-test.nix
git diff --cached --check -- ':!pkgs/any-sync/patches/*.patch'
git commit -m "fix: preserve mixed Any-Sync service accounts"
```

Expected: one commit containing exactly the three files above.

---

### Task 3: Run final focused verification

**Files:**
- Verify: `AGENTS.md`, `nixos/modules/any-sync/common.nix`, `nixos/tests/any-sync-test.nix`
- Test: formatting, flake evaluation, test derivation, and repository state

**Interfaces:**
- Consumes: the committed Task 2 repair.
- Produces: evidence that the mixed override works, project policy matches behavior, and the repaired branch remains evaluable.

- [ ] **Step 1: Re-run Nix formatting checks**

```bash
nixfmt --check nixos/modules/any-sync/common.nix nixos/tests/any-sync-test.nix
```

Expected: exit status `0`.

- [ ] **Step 2: Evaluate the Linux flake outputs without building**

```bash
nix flake check --no-build --system x86_64-linux --show-trace
```

Expected: exit status `0`; `checks.x86_64-linux.any-sync-test` evaluates successfully.

- [ ] **Step 3: Re-run the VM integration test derivation**

```bash
nix build --show-trace --print-build-logs .#checks.x86_64-linux.any-sync-test
```

Expected: exit status `0`.

- [ ] **Step 4: Verify the repair diff and status**

```bash
git diff --check origin/main...HEAD -- ':!pkgs/any-sync/patches/*.patch'
git status --short --branch
```

Expected: no diff-check output; only pre-existing untracked `docs/superpowers/plans/` files may appear.

# Any-Sync NixOS flake ❄️

Flake to natively self-host any-sync infrastructure 
(for [Anytype](https://anytype.io)) on NixOS.

## Goals 📝

- [X] anysync packages
- [ ] configuration modules (added, but not tested yet)
- [ ] add tests (added, but not tested yet)
- [ ] add "HOWTO"
- [ ] merge into NixOS/nixpkgs

## CI/CD and binary cache

- Pull requests and pushes to `main` evaluate supported flake systems and run the NixOS VM integration test.
- A daily workflow updates the five Any-Sync packages together in one pull request. See [package maintenance](docs/update-pkg.md) for failure investigation.
- Trusted `main` workflows publish signed package and reusable Linux VM inputs to an operator-provisioned AWS S3 cache; weekly retention automatically removes obsolete entries. See [AWS binary cache operations and client setup](docs/binary-cache.md) before provisioning or consuming it.

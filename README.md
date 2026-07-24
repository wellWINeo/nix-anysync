# Any-Sync NixOS flake ❄️

Flake to natively self-host any-sync infrastructure 
(for [Anytype](https://anytype.io)) on NixOS.

## Goals 📝

- [X] anysync packages
- [ ] configuration modules (added, but not tested yet)
- [ ] add tests (added, but not tested yet)
- [ ] add "HOWTO"
- [ ] merge into NixOS/nixpkgs

## CI/CD

- Pull requests and pushes to `main` evaluate all supported flake systems with `nix flake check --no-build --all-systems`; package builds and integration tests are not run by this job yet.
- Five GitHub Actions workflows run daily to check for upstream releases.
- New releases trigger issue creation with label `dependency-update`.
- Binary cache uploads go to S3 on Yandex Cloud (see Makefile).

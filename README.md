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

- Pull requests and pushes to `main` evaluate all supported flake systems and run the NixOS VM integration test.
- A daily workflow updates the five Any-Sync packages together in one pull request. See [package maintenance](docs/update-pkg.md) for failure investigation.
- Binary cache uploads go to S3 on Yandex Cloud (see Makefile).

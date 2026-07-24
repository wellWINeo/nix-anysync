# Update any-sync package version

1. Check the remote repository for latest version (`curl -s "https://api.github.com/repos/${ORG]/${PKG}/releases/latest" | jq -r '.tag_name'`)
2. Update version variable in `let` expression
3. Use `nix-prefetch-github --rev ${REV} ${ORG} ${PKG}` to obtain the sha256
4. Update sha256 in `fetchFromGitHub`
5. To update `vendorHash`:
   - clear to `vendorHash = "";`
   - check build logs: `nix build .#${PGK} 2>&1`
   - extraxt hash from logs and update
6. Check build again: `nix build "path:.#${PKG}"`

## Common Gotchas

- When there is a build error `$'\r': command not found`, then run `dos2unix` on the respective file to fix it

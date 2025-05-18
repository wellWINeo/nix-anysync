# Update any-sync package version

1. Update version variable in `let` expression
2. Update sha256 in `fetchFromGitHub`
3. Update `vendorHash`
    ```bash
    git clone ${REPO_URL} # or git pull
    git checkout ${VERSION_TAG} 
    go mod tidy
    go mod vendor
    nix hash path ./vendor
    ```
4. Check build: `nix build "path:.#${PKG}"`
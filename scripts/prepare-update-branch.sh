#!/usr/bin/env bash
set -euo pipefail

base="${1:?expected base branch}"
branch="${2:?expected update branch}"
pr_open="${3:?expected pull request status}"

case "$pr_open" in
  true)
    git switch --create "$branch" --track "origin/$branch"
    git merge --no-edit "origin/$base"
    ;;
  false)
    if git show-ref --verify --quiet "refs/remotes/origin/$branch"; then
      echo "Update branch $branch already exists without an open PR; resolve it manually." >&2
      exit 1
    fi
    git switch --create "$branch"
    ;;
  *) echo "Invalid pull request status: $pr_open" >&2; exit 2 ;;
esac

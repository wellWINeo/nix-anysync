#!/usr/bin/env bash
set -euo pipefail

branches=$(gh pr list --repo "$GITHUB_REPOSITORY" --base "$BASE_BRANCH" \
  --state open --limit 1000 --json headRefName,isCrossRepository \
  --jq '.[] | select((.isCrossRepository == false) and (.headRefName | test("^automation/update-any-sync-stack-[0-9]+-[0-9]+$"))) | .headRefName')
if [[ "$branches" == *$'\n'* ]]; then
  echo 'Multiple open stack update PRs require manual resolution.' >&2
  exit 1
elif [[ -n "$branches" ]]; then
  if [[ ! "$branches" =~ ^automation/update-any-sync-stack-[0-9]+-[0-9]+$ ]]; then
    echo 'Invalid stack update branch.' >&2
    exit 1
  fi
  echo 'open=true' >> "$GITHUB_OUTPUT"
  branch="$branches"
else
  echo 'open=false' >> "$GITHUB_OUTPUT"
  branch="automation/update-any-sync-stack-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
fi
echo "UPDATE_BRANCH=$branch" >> "$GITHUB_ENV"

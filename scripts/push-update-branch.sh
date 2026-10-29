#!/usr/bin/env bash
set -euo pipefail

: "${UPDATE_BRANCH:?expected update branch}"
: "${BASE_BRANCH:?expected base branch}"
: "${PR_OPEN:?expected pull request status}"
: "${GITHUB_REPOSITORY:?expected GitHub repository}"

git push origin "HEAD:refs/heads/$UPDATE_BRANCH"
if [[ "$PR_OPEN" == false ]]; then
  gh pr create --repo "$GITHUB_REPOSITORY" --base "$BASE_BRANCH" --head "$UPDATE_BRANCH" \
    --title 'Update Any-Sync stack' \
    --body 'Update the Any-Sync packages together. Review the changes and PR checks before merging.'
fi

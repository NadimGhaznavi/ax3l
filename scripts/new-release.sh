#!/usr/bin/env bash
# Create and publish an Ax3l release: feature -> dev -> main.

set -e

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

usage() {
    local branch likely_version major minor patch next_version current_version
    branch=$(git branch --show-current)
    if [[ ${branch} =~ (^|[/_-])v?([0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?)$ ]]; then
        likely_version=${BASH_REMATCH[2]}
    else
        current_version=$(sed -nE 's/^    VERSION: Final\[str\] = "([^"]+)"$/\1/p' ax3l/constants/DAx3l.py)
        IFS=. read -r major minor patch <<< "${current_version%%[-+]*}"
        likely_version="${major}.${minor}.$((10#${patch} + 1))"
    fi
    IFS=. read -r major minor patch <<< "${likely_version%%[-+]*}"
    next_version="${major}.${minor}.$((10#${patch} + 1))"

    cat <<EOF
Usage: $(basename -- "$0") <version> <message> [next-feature-branch]

Current branch: ${branch}
Likely next version: ${likely_version}

Example:
  $(basename -- "$0") ${likely_version} "Maintenance release"

Next feature branch: feat/maint-${next_version}

Run from a clean feature branch with local dev and main up to date.
Use a version without a leading v. The next branch defaults to
feat/maint-<version with patch incremented>.

Updates the version and changelog, merges through dev to main, tags and
pushes the release, then creates the next local feature branch.
EOF
}

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
    usage
    exit 0
fi
if [[ $# -lt 2 || $# -gt 3 ]]; then
    usage >&2
    exit 2
fi

version=$1
message="Release ${version}: $2"
tag="v${version}"
IFS=. read -r major minor patch <<< "${version%%[-+]*}"
next_branch=${3:-"feat/maint-${major}.${minor}.$((10#${patch} + 1))"}
source_branch=$(git branch --show-current)
constants_file="ax3l/constants/DAx3l.py"
release_date=$(date '+%Y-%m-%d @ %H:%M')

git fetch --prune --tags origin
git switch dev
git merge --no-ff "${source_branch}" -m "Merge ${source_branch} for ${tag}"

sed -i -E "s/^(    VERSION: Final\[str\] = ).*/\1\"${version}\"/" "${constants_file}"
sed -i "/^## \[Unreleased\]$/a\\
\\
## [${version}] - ${release_date}" CHANGELOG.md
git add -- "${constants_file}" CHANGELOG.md
git commit -m "${message}"

git switch main
git merge --no-ff dev -m "${message}"
git tag -a "${tag}" -m "${message}"

git switch dev
git merge --ff-only main
git push --atomic origin main dev "refs/tags/${tag}"
git switch -c "${next_branch}"

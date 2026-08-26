#!/bin/sh
#
# Creates a top-level commit for the submodules, listing the changes in the
# commit message body.
#
# The script takes a tag or branch to fetch as an argument. If nothing is
# passed, the currently checked out submodule revisions are committed.

set -eu

if [ "${1-}" = "handle-submodule" ]; then
    # Available in submodule foreach: $name, $sm_path, $displaypath, $sha1, $toplevel
    body_file="${BUMP_BODY_FILE}"
    ref="${BUMP_REF}"

    target_branch=""
    if [ -z "${ref}" ]; then
        target="$(git rev-parse HEAD)"
    else
        git fetch --quiet origin --tags
        if git rev-parse --quiet --verify "refs/remotes/origin/${ref}" >/dev/null; then
            target_branch="${ref}"
            target="refs/remotes/origin/${ref}"
        elif git rev-parse --quiet --verify "refs/tags/${ref}" >/dev/null; then
            target="refs/tags/${ref}"
        else
            exit 0
        fi
    fi

    # shellcheck disable=SC2154
    if ! git diff "${sha1}..${target}" --quiet; then
        if added="$(git log "${sha1}..${target}" --pretty=format:"* %s (%h)" | grep -v "Merged PR")"; then
            # shellcheck disable=SC2154
            printf '\n%s:\n%s\n' "${sm_path}" "${added}" >> "${body_file}"
        fi
        if removed="$(git log "${target}..${sha1}" --pretty=format:"* %s (%h)" | grep -v "Merged PR")"; then
            printf '\n%s (removed):\n%s\n' "${sm_path}" "${removed}" >> "${body_file}"
        fi
        if [ -n "${target_branch}" ]; then
            git checkout --quiet "${target_branch}"
            git merge --quiet --ff-only "${target}"
        elif [ -n "${ref}" ]; then
            git checkout --quiet --detach "${target}"
        fi
    fi
    exit 0
fi

if [ $# -gt 1 ]; then
    printf 'Usage: %s [<ref>]\n' "$0" >&2
    exit 1
fi
ref="${1-}"

self="$(readlink -f "$0")"
cd "$(dirname "${self}")"
cd "$(git rev-parse --show-toplevel)"

if [ -n "${ref}" ] && ! git diff --quiet; then
    echo "Repository is not clean!" >&2
    exit 1
fi

body_file=$(mktemp)
trap 'rm -f "${body_file}"' EXIT TERM INT
echo "Update submodule(s)" > "${body_file}"

# git submodule foreach joins its arguments into a shell command line and only
# exports $sha1 and $sm_path for the single-string form. The environment keeps
# our values out of that line.
BUMP_SCRIPT="${self}"
BUMP_BODY_FILE="${body_file}"
BUMP_REF="${ref}"
export BUMP_SCRIPT BUMP_BODY_FILE BUMP_REF
git submodule foreach 'export sha1 sm_path; "${BUMP_SCRIPT}" handle-submodule'

if git diff --quiet; then
    echo "All submodules are already up-to-date"
    exit 0
fi

git commit -eF "${body_file}" .

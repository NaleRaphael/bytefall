#!/bin/bash
set -e

PY_VER=`python -c \
        "from sys import version_info as ver; \
        print('py%s%s' % (ver.major, ver.minor))"`
GIT_BRANCH="cov-$PY_VER"
COVERAGE_FILE=".coverage.$PY_VER"
MODULE_NAME="bytefall"  # XXX: variable for "run_tests_with_coverage"

THIS_DIR=`dirname $0`
source "$THIS_DIR"/utils.sh

# -----
setup_git_for_travis
setup_git_upstream
exist=`check_branch_exists`

if [ $exist -eq 0 ]; then
    create_branch_for_coverage "$GIT_BRANCH"
fi

pull_branch_for_coverage "$GIT_BRANCH"
run_tests_with_coverage --runslow
commit_artifacts "$GIT_BRANCH" "$COVERAGE_FILE"
push_artifacts "$GIT_BRANCH"

#!/bin/bash
set -e

THIS_DIR=`dirname $0`
source ${THIS_DIR}/utils.sh

setup_git_for_travis
setup_git_upstream

declare -a py_vers=('34' '35' '36' '37' '38')

for ver in "${py_vers[@]}"
do
    pull_branch_for_coverage "cov-py${ver}"
    checkout_coverage_file_from_branch "cov-py${ver}" ".coverage.py${ver}"
done

combine_coverage_files
generate_coverage_html
publish_coverage_html

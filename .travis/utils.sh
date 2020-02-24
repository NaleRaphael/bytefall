#!/bin/bash

setup_git_for_travis() {
    git config user.email "travis@travis-ci.org"
    git config user.name "Travis CI"
}

setup_git_upstream() {
    git remote set-url origin \
        https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${GITHUB_REPO}.git
}

check_branch_exists() {
    local user=${1:-"$GITHUB_USER"}
    local repo=${2:-"$GITHUB_REPO"}
    local branch=${3:-"$GIT_BRANCH"}
    echo `git ls-remote --heads \
        https://github.com/${user}/${repo}.git \
        ${branch} \
        | wc -l`
}

create_branch_for_coverage() {
    local branch=$1
    git checkout -q --orphan "$branch"
    git rm -rf -q .
    git commit -q --allow-empty -m "root commit for coverage file"
    git push -q -u origin "$branch"
    git checkout -q master
}

pull_branch_for_coverage() {
    local branch=$1
    git fetch -q origin "$branch":"$branch"
    git checkout -q "$branch"
    git checkout -q master     # go back to master
}

commit_artifacts() {
    local branch=$1
    local file=$2
    git checkout -q $branch
    git add "$file"
    # NOTE: In case that nothing changed in current commit,
    # we should allow empty commit
    git commit -q --allow-empty -m "Travis build: $TRAVIS_BUILD_NUMBER"
    git checkout -q master
}

push_artifacts() {
    local branch=$1
    git push -q origin $branch
}

run_tests_with_coverage() {
    local coverage_file=${COVERAGE_FILE:-".coverage"}
    local module_name=$MODULE_NAME
    COVERAGE_FILE="$coverage_file" python -mpytest \
        --cov-config=.coveragerc \
        --cov=$module_name \
        ./tests/ "$@"
}

checkout_coverage_file_from_branch() {
    # $1: branch name, e.g. cov-pyXX
    # $2: name of coverage file, e.g. .coverage.pyXX
    git checkout -q $1 -- $2
    mkdir -p "coverage_data"
    mv $2 "coverage_data"/$2
}

combine_coverage_files() {
    cd "coverage_data" && python -mcoverage combine
    cd ..
    mv "coverage_data/.coverage" ".coverage"
}

generate_coverage_html() {
    python -mcoverage html
}

publish_coverage_html() {
    local user=${1:-"$GITHUB_USER"}
    local repo=${2:-"$GITHUB_REPO"}
    local branch_name="gh-pages"
    local html_dir="coverage_html_report"
    local exist=`git ls-remote --heads \
        https://github.com/${user}/${repo}.git \
        ${branch_name} | wc -l`

    if [ $exist -eq 0 ]; then
        git checkout -q --orphan "$branch_name"
        git rm -rf -q .
        git commit -q --allow-empty -m "root commit for coverage report"
        git push -q -u origin "$branch_name"
        git checkout -q master
    fi

    # remember to fetch branch before checking out
    pull_branch_for_coverage "$branch_name"

    git checkout -q "$branch_name"
    git add ./"$html_dir"
    git mv -f ./"$html_dir"/* ./

    # XXX: exclude coverage files that just being checked out by
    # previous command `checkout_coverage_file_from_branch`
    git reset -- .coverage.*
    git commit -q --allow-empty -m "Travis build: $TRAVIS_BUILD_NUMBER"
    git push -q origin "$branch_name"
    git checkout -q master
}

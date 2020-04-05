#!/bin/bash
set -e

COVERAGE_FILE=".coverage"  # use the same filename for codecov
MODULE_NAME="bytefall"  # XXX: variable for "run_tests_with_coverage"

THIS_DIR=`dirname $0`
source "$THIS_DIR"/utils.sh

# -----
run_tests_with_coverage --runslow

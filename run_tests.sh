#!/usr/bin/env bash
# Run the CometChat Dashboard E2E suite and build the HTML report.
#
#   ./run_tests.sh                                    # everything
#   ./run_tests.sh modules/general/overview           # one module
#   ./run_tests.sh modules/general/user_and_groups/users
#   ./run_tests.sh -k "USR_081 or OV_052"             # security checks only
set -uo pipefail

cd "$(dirname "$0")"

export CC_BASE_URL="${CC_BASE_URL:-https://app.cometchat.com}"
export CC_APP_ID="${CC_APP_ID:-1671876b17a071c54}"
export CC_STORAGE_STATE="${CC_STORAGE_STATE:-$(pwd)/auth/storage_state.json}"
export CC_HEADLESS="${CC_HEADLESS:-1}"
export CC_E2E_PREFIX="${CC_E2E_PREFIX:-e2e}"

echo "==> App:    $CC_APP_ID"
echo "==> Auth:   $CC_STORAGE_STATE"
echo "==> Prefix: $CC_E2E_PREFIX  (test data is created and deleted under this prefix)"
echo

python3 -m pytest "$@"
STATUS=$?

echo
echo "==> Building HTML report"
python3 utils/report.py reports/results.json reports/report.html

exit $STATUS

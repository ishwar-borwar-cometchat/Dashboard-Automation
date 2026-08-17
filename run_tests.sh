#!/usr/bin/env bash
# Run the CometChat Dashboard Overview E2E suite and build the HTML report.
set -uo pipefail

cd "$(dirname "$0")"

export CC_BASE_URL="${CC_BASE_URL:-https://app.cometchat.com}"
export CC_APP_ID="${CC_APP_ID:-1671876b17a071c54}"
export CC_STORAGE_STATE="${CC_STORAGE_STATE:-$(pwd)/auth/storage_state.json}"
export CC_HEADLESS="${CC_HEADLESS:-1}"

echo "==> App:   $CC_APP_ID"
echo "==> Auth:  $CC_STORAGE_STATE"
echo

python3 -m pytest "$@"
STATUS=$?

echo
echo "==> Building HTML report"
python3 utils/report.py reports/results.json reports/overview_report.html

exit $STATUS

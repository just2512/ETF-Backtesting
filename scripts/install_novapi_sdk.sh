#!/usr/bin/env bash
set -euo pipefail

# Pinned official Linux SDK distribution. Verify the exact release asset before
# extracting native code into the ephemeral GitHub Actions runner.
readonly URL='https://github.com/hello245m/free-stockdb/releases/download/%E6%B5%8B%E8%AF%95%E7%89%88%E6%9C%AC0.3.5/free-stockdb-manylinux-x64-v0.3.5-more-power.tar'
readonly SHA256='9ec47250f60cd35462446dfcf34db99ef33e6b73b3f02f0970ef329722c265cf'
readonly DEST="${1:-${RUNNER_TEMP:-/tmp}/novapi-stock-sdk}"
readonly ARCHIVE="${RUNNER_TEMP:-/tmp}/novapi-stock-sdk.tar"

mkdir -p "$DEST"
curl --fail --location --retry 3 --retry-all-errors "$URL" --output "$ARCHIVE"
echo "$SHA256  $ARCHIVE" | sha256sum --check -
tar -xf "$ARCHIVE" -C "$DEST"

SDK_FILE="$(find "$DEST" -type f -name 'stock_sdk.py' -print -quit)"
if [[ -z "$SDK_FILE" ]]; then
  echo "Official Linux distribution does not contain stock_sdk.py" >&2
  find "$DEST" -maxdepth 4 -type f -print >&2
  exit 20
fi
SDK_ROOT="$(dirname "$SDK_FILE")"
if ! find "$SDK_ROOT" -maxdepth 2 -type f \( -name 'stockdb*.so' -o -name 'stockdb*.abi3.so' \) -print -quit | grep -q .; then
  echo "stock_sdk.py found but matching Linux stockdb shared library is missing" >&2
  find "$DEST" -maxdepth 4 -type f -print >&2
  exit 21
fi

if [[ -n "${GITHUB_ENV:-}" ]]; then
  echo "PYTHONPATH=$SDK_ROOT:${PYTHONPATH:-}" >> "$GITHUB_ENV"
fi
export PYTHONPATH="$SDK_ROOT:${PYTHONPATH:-}"

python - <<'PY'
import importlib
sdk = importlib.import_module("stock_sdk")
required = ("set_init", "get_price", "get_trade_days", "get_index_stocks", "get_index_weights")
missing = [name for name in required if not callable(getattr(sdk, name, None))]
if missing:
    raise SystemExit(
        "The downloaded stock_sdk build does not expose the NovAPI online RemoteProxy API; "
        f"missing={missing}. Refusing to substitute the local-only SDK."
    )
print("NovAPI SDK import contract PASS:", ", ".join(required))
PY

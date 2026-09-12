#!/usr/bin/env bash
#
# Run a script with the project's virtualenv interpreter.
#
# The engine imports pandas and numpy, which the system python3 usually does not
# have, so `npm run screen` used to die with ModuleNotFoundError. This says what
# to do instead. Set PARITY_PYTHON to use a different interpreter.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PARITY_PYTHON:-${ROOT}/.venv/bin/python}"

if [[ ! -x "${PYTHON}" ]]; then
  cat >&2 <<MESSAGE
This needs the project's virtualenv, which is missing:
  ${PYTHON}

Create it once with:
  python3 -m venv .venv
  .venv/bin/pip install -r requirements-test.txt     # offline runs and tests
  .venv/bin/pip install -r requirements-network.txt  # adds live prices and the NSE refresh

Or point PARITY_PYTHON at an interpreter that has pandas and numpy.
MESSAGE
  exit 1
fi

exec "${PYTHON}" "$@"

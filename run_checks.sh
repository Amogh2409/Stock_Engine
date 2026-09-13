#!/usr/bin/env bash
#
# Strict release gate for the Indian Equity Screening Engine.
#
# Every step below is mandatory. There is no `|| true` on any required check --
# the only tolerated failures are inside the cleanup trap, where a best-effort
# teardown is correct. If any check fails the script aborts immediately, prints
# the failing command and its output, and does NOT create a release archive.
#
# Artefacts are produced only after every check has passed, including a full
# re-verification inside a freshly extracted copy of the archive.
#
# Usage:  bash run_checks.sh
#         KEEP_WORKDIR=1 bash run_checks.sh    (retain the temp dirs for triage)
set -euo pipefail

RELEASE_NAME="indian_equity_engine_v6_clean"
NOTEBOOK="Indian_Equity_Quantitative_Engine.ipynb"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT="${SOURCE_DIR}/verification_report.txt"

# The README tells you to set this to move the data store. Tests assert the
# default location, so the gate must not inherit it.
unset TRADEBOT_DATA_DIR

WORK_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/iese-verify-XXXXXX")"
BUILD_DIR="${WORK_ROOT}/build"       # isolated copy that gets verified
REPACK_DIR="${WORK_ROOT}/repack"     # archive extracted again and re-verified
VENV_DIR="${WORK_ROOT}/venv"
SERVER_PID=""
# step()/step_in() run in subshells, so the current step is tracked in a file
# that the EXIT trap can read back.
STATE_DIR="${WORK_ROOT}/.state"
mkdir -p "${STATE_DIR}"
echo 0 > "${STATE_DIR}/index"
echo "startup" > "${STATE_DIR}/step"

next_step_index() {
  local n
  n=$(( $(cat "${STATE_DIR}/index") + 1 ))
  echo "${n}" > "${STATE_DIR}/index"
  printf '%s' "${n}"
}
mark_step() { printf '%s' "$1" > "${STATE_DIR}/step"; }
current_step() { cat "${STATE_DIR}/step" 2>/dev/null || echo "<unknown>"; }

# ---------------------------------------------------------------------------
# Cleanup. `|| true` is acceptable here and only here.
# ---------------------------------------------------------------------------
cleanup() {
  local exit_code=$?
  # EXIT fires after INT/TERM, so without this guard Ctrl-C printed the failure
  # banner twice.
  if [[ "${CLEANUP_DONE:-0}" == "1" ]]; then return; fi
  CLEANUP_DONE=1
  # Read the failing step BEFORE the work directory (which holds the state
  # file) is removed, otherwise every failure reports "<unknown>".
  local failed_step
  failed_step="$(current_step)"
  if [[ -n "${SERVER_PID}" ]]; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
  if [[ "${KEEP_WORKDIR:-0}" == "1" ]]; then
    echo ""
    echo "Work directory retained: ${WORK_ROOT}"
  else
    rm -rf "${WORK_ROOT}" 2>/dev/null || true
  fi
  if [[ ${exit_code} -ne 0 ]]; then
    echo ""
    echo "=============================================================="
    echo "VERIFICATION FAILED at step: ${failed_step}"
    echo "Exit code: ${exit_code}"
    echo "No release archive was created."
    echo "=============================================================="
  fi
  exit ${exit_code}
}
trap cleanup EXIT INT TERM

log() { printf '\n%s\n' "$*" | tee -a "${REPORT}"; }
raw() { printf '%s\n' "$*" >> "${REPORT}"; }

# Run a required command: stream output, append to the report, abort on failure.
step() {
  local title="$1"; shift
  local idx
  idx="$(next_step_index)"
  mark_step "${idx}. ${title}"
  printf '\n--- STEP %02d: %s ---\n' "${idx}" "${title}" | tee -a "${REPORT}"
  raw "\$ $*"
  local output status
  set +e
  output="$("$@" 2>&1)"
  status=$?
  set -e
  printf '%s\n' "${output}" | tee -a "${REPORT}"
  raw "exit code: ${status}"
  if [[ ${status} -ne 0 ]]; then
    echo "REQUIRED CHECK FAILED: ${title}" | tee -a "${REPORT}"
    return ${status}
  fi
  return 0
}

# Same, but executed with a specific working directory.
step_in() {
  local dir="$1"; local title="$2"; shift 2
  ( cd "${dir}" && step "${title}" "$@" )
}

# ---------------------------------------------------------------------------
: > "${REPORT}"
raw "INDIAN EQUITY SCREENING ENGINE - RELEASE VERIFICATION REPORT"
raw "==========================================================="
raw "Generated (UTC): $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
raw "Source directory: ${SOURCE_DIR}"
raw "Isolated build directory: ${BUILD_DIR}"
raw "Every check below is mandatory; no required step uses '|| true'."

log "--- ENVIRONMENT ---"
raw "uname:  $(uname -srm)"
raw "node:   $(node --version)"
raw "npm:    $(npm --version)"
raw "python: $(python3 --version 2>&1)"
raw "bash:   ${BASH_VERSION}"

# 1. Isolated copy of the source tree (no node_modules, dist, caches or archives).
mark_step "$(next_step_index). create isolated working copy"
log "--- STEP: create isolated working copy ---"
mkdir -p "${BUILD_DIR}"
tar -C "${SOURCE_DIR}" \
    --exclude='./node_modules' --exclude='./dist' --exclude='./dist-server' --exclude='./.git' \
    --exclude='./__pycache__' --exclude='*.pyc' --exclude='./IndianStockEngine' \
    --exclude='./_test_cache' --exclude='*.zip' --exclude='*.sha256' \
    --exclude='./.venv' --exclude='./venv' --exclude='./coverage' \
    --exclude='./Books_TO_study' \
    -cf - . | tar -C "${BUILD_DIR}" -xf -
# The data-store holds run output (CSVs, snapshots, logs). Its structure is
# part of the release; its contents never are.
if [[ -d "${BUILD_DIR}/data-store" ]]; then
  find "${BUILD_DIR}/data-store" -type f ! -name '.gitkeep' ! -name 'README.md' -delete
fi
raw "copied $(find "${BUILD_DIR}" -type f | wc -l | tr -d ' ') files into the isolated directory"

# 2-3. Throwaway virtualenv with exactly the pinned dependencies.
step_in "${BUILD_DIR}" "create throwaway python virtualenv" python3 -m venv "${VENV_DIR}"
VENV_PY="${VENV_DIR}/bin/python"
step_in "${BUILD_DIR}" "upgrade pip in the virtualenv" "${VENV_PY}" -m pip install --quiet --upgrade pip
step_in "${BUILD_DIR}" "install pinned python dependencies" \
  "${VENV_PY}" -m pip install --quiet --require-virtualenv -r "${BUILD_DIR}/requirements-test.txt"
step_in "${BUILD_DIR}" "record installed python packages" "${VENV_PY}" -m pip freeze
export PARITY_PYTHON="${VENV_PY}"
raw "PARITY_PYTHON=${PARITY_PYTHON}"

# 4. Reproducible node install from the lockfile.
step_in "${BUILD_DIR}" "npm ci" npm ci

# 5. Dependency audit at high severity.
step_in "${BUILD_DIR}" "npm audit --audit-level=high" npm audit --audit-level=high

# 6. Codegen sync + TypeScript lint.
step_in "${BUILD_DIR}" "python codegen is in sync" npm run check:python
step_in "${BUILD_DIR}" "typescript lint (tsc --noEmit)" npm run lint

# 7. Frontend + cross-engine test suite (includes the parity suite).
step_in "${BUILD_DIR}" "frontend and parity test suite" npm test

# 8. Production build.
step_in "${BUILD_DIR}" "production build" npm run build

# 9-10. Regenerate the notebook and byte-compare it with the shipped copy.
mark_step "$(next_step_index). regenerate notebook and byte-compare"
log "--- STEP: regenerate notebook and byte-compare with the shipped copy ---"
cp "${BUILD_DIR}/${NOTEBOOK}" "${WORK_ROOT}/shipped_notebook.ipynb"
( cd "${BUILD_DIR}" && npm run generate:notebook ) 2>&1 | tee -a "${REPORT}"
if ! cmp -s "${WORK_ROOT}/shipped_notebook.ipynb" "${BUILD_DIR}/${NOTEBOOK}"; then
  {
    echo "REQUIRED CHECK FAILED: the shipped notebook differs from the one"
    echo "generated by the current TypeScript. Run: npm run generate:notebook"
    cmp "${WORK_ROOT}/shipped_notebook.ipynb" "${BUILD_DIR}/${NOTEBOOK}" || true
  } | tee -a "${REPORT}"
  exit 1
fi
raw "byte comparison: identical"

# 11. Compile every notebook code cell with Python.
step_in "${BUILD_DIR}" "compile every notebook code cell" "${VENV_PY}" - <<'PYEOF'
import json, sys
from pathlib import Path

path = Path("Indian_Equity_Quantitative_Engine.ipynb")
notebook = json.loads(path.read_text(encoding="utf-8"))
cells = [c for c in notebook["cells"] if c["cell_type"] == "code"]
if not cells:
    print("FAILED: notebook has no code cells")
    sys.exit(1)
total = 0
for index, cell in enumerate(cells):
    source = "".join(cell["source"])
    if not source.strip():
        print("FAILED: code cell %d is empty" % index)
        sys.exit(1)
    compile(source, "cell-%d" % index, "exec")
    total += source.count("\n") + 1
print("compiled %d code cell(s), %d python lines" % (len(cells), total))
PYEOF

# 12. Offline python test suite (notebook EngineTests + standalone contracts).
step_in "${BUILD_DIR}" "offline python test suite" "${VENV_PY}" test_python.py

# 12a. The backtest's own mechanics: look-ahead, execution timing, cost accounting,
# p-values from t, Bonferroni. This is the only code that measures whether the
# engine predicts anything, and until now it was the only code outside the gate
# everything else must pass -- so a change that silently broke the measurement
# would have shipped green. Offline and fixture-driven: no prices, no network.
step_in "${BUILD_DIR}" "backtest self-test" "${VENV_PY}" python/backtest.py --self-test

# 13. Cross-engine sample parity, run explicitly as its own gate.
step_in "${BUILD_DIR}" "cross-engine sample parity suite" npx vitest run src/tests/parity.test.ts

# 14-16. Production server smoke test.
mark_step "$(next_step_index). production server smoke test"
log "--- STEP: production server smoke test ---"
# Pick a port that is genuinely free, so a leaked process from an earlier run
# can never answer this smoke test.
PORT=""
for candidate in $(seq 8731 8760); do
  if ! (exec 3<>"/dev/tcp/127.0.0.1/${candidate}") 2>/dev/null; then
    PORT="${candidate}"
    break
  fi
done
if [[ -z "${PORT}" ]]; then
  echo "REQUIRED CHECK FAILED: no free port in 8731-8760 for the smoke test" | tee -a "${REPORT}"
  exit 1
fi

( cd "${BUILD_DIR}" && NODE_ENV=production PORT="${PORT}" node dist-server/server.cjs >"${WORK_ROOT}/server.log" 2>&1 & echo $! > "${WORK_ROOT}/server.pid" )
SERVER_PID="$(cat "${WORK_ROOT}/server.pid")"
raw "server pid ${SERVER_PID} on port ${PORT}"

ready=0
for _ in $(seq 1 60); do
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
    { echo "REQUIRED CHECK FAILED: server process exited during startup"; cat "${WORK_ROOT}/server.log"; } | tee -a "${REPORT}"
    exit 1
  fi
  if curl -fsS "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then ready=1; break; fi
  sleep 0.25
done
if [[ ${ready} -ne 1 ]]; then
  { echo "REQUIRED CHECK FAILED: server did not become ready"; cat "${WORK_ROOT}/server.log"; } | tee -a "${REPORT}"
  exit 1
fi

HEALTH="$(curl -fsS "http://127.0.0.1:${PORT}/api/health")"
raw "GET /api/health -> ${HEALTH}"
if [[ "${HEALTH}" != *'"ok"'* ]]; then
  echo "REQUIRED CHECK FAILED: /api/health did not report ok" | tee -a "${REPORT}"
  exit 1
fi
for route in "/" "/inspection/nested/spa-route"; do
  code="$(curl -fsS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}${route}")"
  raw "GET ${route} -> HTTP ${code}"
  if [[ "${code}" != "200" ]]; then
    echo "REQUIRED CHECK FAILED: ${route} returned HTTP ${code}, expected 200" | tee -a "${REPORT}"
    exit 1
  fi
done
kill "${SERVER_PID}" 2>/dev/null || true
wait "${SERVER_PID}" 2>/dev/null || true
for _ in $(seq 1 40); do
  if ! (exec 3<>"/dev/tcp/127.0.0.1/${PORT}") 2>/dev/null; then break; fi
  sleep 0.25
done
SERVER_PID=""
raw "server stopped and port ${PORT} released"

# 17. Build the release archive from the verified tree.
mark_step "$(next_step_index). build release archive"
log "--- STEP: build release archive ---"
STAGE="${WORK_ROOT}/${RELEASE_NAME}"
mkdir -p "${STAGE}"
while IFS= read -r item; do
  [[ -e "${BUILD_DIR}/${item}" ]] || { echo "REQUIRED FILE MISSING: ${item}" | tee -a "${REPORT}"; exit 1; }
  cp -R "${BUILD_DIR}/${item}" "${STAGE}/"
done <<'MANIFEST'
src
python
scripts
data
data-store
index.html
package.json
package-lock.json
tsconfig.json
vite.config.ts
vitest.config.ts
server.ts
generate_ipynb.ts
metadata.json
requirements-test.txt
requirements-network.txt
run_checks.sh
test_python.py
README.md
.env.example
.gitignore
Indian_Equity_Quantitative_Engine.ipynb
MANIFEST

find "${STAGE}" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "${STAGE}" -name '*.pyc' -delete 2>/dev/null || true
# Ship the data-store skeleton only -- never anyone's exports, reports or logs.
if [[ -d "${STAGE}/data-store" ]]; then
  find "${STAGE}/data-store" -type f ! -name '.gitkeep' ! -name 'README.md' -delete
  for sub in config fundamentals market_data cache reports watchlists logs; do
    mkdir -p "${STAGE}/data-store/${sub}"
    touch "${STAGE}/data-store/${sub}/.gitkeep"
  done
fi

# Built inside the work directory. Nothing is written beside the source until
# every check has passed, so a failed run can never leave an unverified zip
# next to a stale checksum.
ARCHIVE="${WORK_ROOT}/${RELEASE_NAME}.zip"
FINAL_ARCHIVE="${SOURCE_DIR}/${RELEASE_NAME}.zip"
( cd "${WORK_ROOT}" && zip -q -r -X "${ARCHIVE}" "${RELEASE_NAME}" )
raw "archive built in the work directory ($(wc -c < "${ARCHIVE}" | tr -d ' ') bytes)"

# 18. Extract the archive somewhere else and repeat the mandatory checks.
mark_step "$(next_step_index). re-verify inside a freshly extracted archive"
log "--- STEP: re-verify inside a freshly extracted copy of the archive ---"
mkdir -p "${REPACK_DIR}"
( cd "${REPACK_DIR}" && unzip -q "${ARCHIVE}" )
FRESH="${REPACK_DIR}/${RELEASE_NAME}"
[[ -d "${FRESH}" ]] || { echo "REQUIRED CHECK FAILED: archive did not extract" | tee -a "${REPORT}"; exit 1; }

for forbidden in node_modules dist dist-server __pycache__; do
  if [[ -e "${FRESH}/${forbidden}" ]]; then
    echo "REQUIRED CHECK FAILED: archive contains ${forbidden}" | tee -a "${REPORT}"
    exit 1
  fi
done
# -print -quit rather than a pipe into grep: a pipe can exit 141 on SIGPIPE,
# which reads as "nothing found" and silently passes the check.
FORBIDDEN_FOUND="$(find "${FRESH}" \( -name '*.zip' -o -name 'get-pip.py' -o -name 'patch_*.py' \) -print -quit)"
if [[ -n "${FORBIDDEN_FOUND}" ]]; then
  { echo "REQUIRED CHECK FAILED: archive contains excluded artefacts"; echo "${FORBIDDEN_FOUND}"; } | tee -a "${REPORT}"
  exit 1
fi
leaked="$(find "${FRESH}/data-store" -type f ! -name '.gitkeep' ! -name 'README.md' 2>/dev/null | head -5 || true)"
if [[ -n "${leaked}" ]]; then
  { echo "REQUIRED CHECK FAILED: archive contains run data under data-store:"; echo "${leaked}"; } | tee -a "${REPORT}"
  exit 1
fi
for sub in config fundamentals market_data cache reports watchlists logs; do
  if [[ ! -d "${FRESH}/data-store/${sub}" ]]; then
    echo "REQUIRED CHECK FAILED: archive is missing data-store/${sub}" | tee -a "${REPORT}"
    exit 1
  fi
done
raw "archive exclusion checks passed (data-store skeleton present, no run data)"

step_in "${FRESH}" "[repack] npm ci" npm ci
step_in "${FRESH}" "[repack] python codegen is in sync" npm run check:python
step_in "${FRESH}" "[repack] typescript lint" npm run lint
step_in "${FRESH}" "[repack] frontend and parity test suite" npm test
step_in "${FRESH}" "[repack] production build" npm run build
step_in "${FRESH}" "[repack] offline python test suite" "${VENV_PY}" test_python.py
step_in "${FRESH}" "[repack] backtest self-test" "${VENV_PY}" python/backtest.py --self-test

mark_step "[repack] notebook byte comparison"
log "--- STEP: [repack] regenerate notebook and byte-compare ---"
cp "${FRESH}/${NOTEBOOK}" "${WORK_ROOT}/repack_notebook.ipynb"
( cd "${FRESH}" && npm run generate:notebook ) 2>&1 | tee -a "${REPORT}"
if ! cmp -s "${WORK_ROOT}/repack_notebook.ipynb" "${FRESH}/${NOTEBOOK}"; then
  echo "REQUIRED CHECK FAILED: notebook drifted inside the extracted archive" | tee -a "${REPORT}"
  exit 1
fi
raw "byte comparison inside extracted archive: identical"

# 19. Hashes and provenance, produced only now that everything has passed.
mark_step "$(next_step_index). finalise report and generate hashes"
log "--- STEP: notebook hash and provenance ---"
sha_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}';
  else shasum -a 256 "$1" | awk '{print $1}'; fi
}
NOTEBOOK_SHA="$(sha_of "${BUILD_DIR}/${NOTEBOOK}")"
raw "notebook sha256: ${NOTEBOOK_SHA}"

log "--- TEST TOTALS ---"
# Read from the report the suites already wrote. Running both suites a third
# time just to scrape one line each doubled the slowest part of the gate.
FRONTEND_TOTALS="$(grep -E '^\s+Tests ' "${REPORT}" | tail -1)"
PYTHON_TOTALS="$(grep -E '^ran=' "${REPORT}" | tail -1)"
raw "frontend/parity: ${FRONTEND_TOTALS:-not recorded}"
raw "python:          ${PYTHON_TOTALS:-not recorded}"

log "--- NIFTY 100 SNAPSHOT PROVENANCE ---"
"${VENV_PY}" - "${BUILD_DIR}/data/nifty100_snapshot.json" >> "${REPORT}" <<'PYEOF'
import json, sys
snap = json.load(open(sys.argv[1]))
print("source_url:            %s" % snap["source_url"])
print("retrieved_at_utc:      %s" % snap["retrieved_at_utc"])
print("as_of_date:            %s" % snap["as_of_date"])
print("sha256_of_source_csv:  %s" % snap["sha256_of_source_csv"])
print("symbol_count:          %d (unique: %d)" % (snap["count"], len(set(snap["symbols"]))))
print("note: cached snapshot, not a live feed; the index is rebalanced periodically.")
PYEOF

log "--- ARCHIVE LISTING ---"
# List from the archive itself. Enumerating the extracted directory would pick
# up the node_modules that the re-verification step installed there.
unzip -Z1 "${ARCHIVE}" | sort >> "${REPORT}"
raw "total entries in archive: $(unzip -Z1 "${ARCHIVE}" | wc -l | tr -d ' ')"

log "--- DOCUMENTED LIMITATIONS ---"
cat >> "${REPORT}" <<'LIMITS'
1. On-demand only. There is no continuous monitoring or scheduling.
2. Fundamentals are refreshed manually by exporting CSV from Screener.in.
   CSV is the only supported input format; XLSX is rejected by design.
3. Price history comes from yfinance, an unofficial data source, and is used
   only for the separate technical-confirmation score. The browser cannot
   download it; a price-history CSV (the Python run saves one) is uploaded.
4. The bundled Nifty 100 list is a cached snapshot with recorded provenance.
   It is refreshed from NSE at runtime when the network is reachable; offline
   runs clearly report it as cached and dated.
5. Financial-sector companies (banks, NBFCs, insurers, brokers) are explicitly
   out of scope and are always rejected.
6. Scores are deterministic, rule-based research signals to one decimal place.
   They are not price predictions and no orders are ever placed.
7. Technical indicators require sufficient history: SMA50 needs 50 sessions,
   SMA200 needs 200, the 52-week high needs a full 252. Missing indicators
   score zero rather than being approximated.
LIMITS

# The archive was re-verified WITHOUT this report (a report cannot contain its
# own archive's hash). The report is the only file added afterwards, and the
# published SHA-256 below covers the final archive including it.
mark_step "$(next_step_index). add report to archive and hash"
log "--- STEP: add the finalised report to the archive, then hash ---"
raw "note: verification_report.txt is added after re-verification; it is the"
raw "      only difference between the re-verified tree and the final archive."
cp "${REPORT}" "${STAGE}/verification_report.txt"
( cd "${WORK_ROOT}" && zip -q -X "${ARCHIVE}" "${RELEASE_NAME}/verification_report.txt" )
ARCHIVE_SHA="$(sha_of "${ARCHIVE}")"
# Only now, with every check passed, does anything appear beside the source.
# The old checksum goes first, so a stale one can never outlive its zip.
rm -f "${FINAL_ARCHIVE}" "${FINAL_ARCHIVE}.sha256"
cp "${ARCHIVE}" "${FINAL_ARCHIVE}"
printf '%s  %s\n' "${ARCHIVE_SHA}" "${RELEASE_NAME}.zip" > "${FINAL_ARCHIVE}.sha256"
raw "archive file:    ${RELEASE_NAME}.zip"
raw "archive bytes:   $(wc -c < "${ARCHIVE}" | tr -d ' ')"
raw "archive sha256:  ${ARCHIVE_SHA}"
raw "sha256 sidecar:  ${RELEASE_NAME}.zip.sha256"
raw "note: this report is embedded in the archive above; the sha256 covers the"
raw "      final archive including this report."

log "=============================================================="
log "ALL REQUIRED CHECKS PASSED"
log "Archive: ${ARCHIVE}"
log "SHA-256: ${ARCHIVE_SHA}"
log "Report:  ${REPORT}"
log "=============================================================="
mark_step "completed"

#!/bin/bash
# Publish this machine's training results so they can be read from another machine.
# Run from the repository root:   bash tools/local_model/sync_results.sh
#
# Writes output/train/{report.txt,examples.jsonl,rejected.jsonl,errors.jsonl} and the
# benchmark reports in output/ai_eval/ as one commit on the branch "train-results" and
# pushes it. Your checkout is not touched: no branch switch, nothing staged, and the main
# branch (the live site) is never pushed. "[skip ci]" keeps the host from building it.
#
# The branch holds generated requests and designs only — no keys, no user data.
set -euo pipefail
cd "$(dirname "$0")/../.."

REMOTE="${LASERMCP_RESULTS_REMOTE:-origin}"
BRANCH="train-results"
PY=".venv/bin/python"
[ -x "$PY" ] || PY=".venv/Scripts/python.exe"

"$PY" tools/train.py report >/dev/null

files=()
for f in output/train/report.txt output/train/examples.jsonl output/train/rejected.jsonl output/train/errors.jsonl output/ai_eval/*.json; do
  [ -f "$f" ] && files+=("$f")
done
if [ "${#files[@]}" -eq 0 ]; then
  echo "nothing to send yet: run tools/train.py collect first"
  exit 1
fi

# Build the commit with a throwaway index, so the real index and working tree stay as they are.
export GIT_INDEX_FILE
GIT_INDEX_FILE="$(mktemp)"
trap 'rm -f "$GIT_INDEX_FILE"' EXIT
rm -f "$GIT_INDEX_FILE"
for f in "${files[@]}"; do
  blob="$(git hash-object -w "$f")"
  git update-index --add --cacheinfo "100644,$blob,${f#output/}"
done
tree="$(git write-tree)"

# Track the published branch under our own ref name, so this works for any remote spelling.
LOCAL_REF="refs/lasermcp/$BRANCH"
git fetch --quiet "$REMOTE" "+refs/heads/$BRANCH:$LOCAL_REF" 2>/dev/null || true
parent="$(git rev-parse --quiet --verify "$LOCAL_REF" || true)"
if [ -n "$parent" ] && [ "$(git rev-parse "$parent^{tree}")" = "$tree" ]; then
  echo "already up to date"
  exit 0
fi
commit="$(git commit-tree "$tree" ${parent:+-p "$parent"} -m "Training results from $(hostname -s 2>/dev/null || hostname) [skip ci]")"
git push --quiet "$REMOTE" "$commit:refs/heads/$BRANCH"
git update-ref "$LOCAL_REF" "$commit"
echo "sent ${#files[@]} file(s) to $REMOTE/$BRANCH"

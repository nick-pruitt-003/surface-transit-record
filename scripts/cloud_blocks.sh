#!/bin/bash
# Cloud job: six-block tables, assembler over every block order, router re-check of the top 30. Results in docs/.
cd "$(dirname "$0")"
push () { git add ../docs/blocks_log.txt ../docs/assemble.txt ../docs/block_verify.txt 2>/dev/null; git commit -qm "cloud result: $1" || true; for i in 1 2 3; do git pull -q --rebase && git push -q && return 0; sleep 5; done; echo "PUSH FAILED $1"; }
mkdir -p ../out
python3 -u blocks.py > ../docs/blocks_log.txt 2>&1 || { echo "BLOCKS FAILED"; push blocks-failed; exit 2; }
push blocks
python3 -u assemble.py > /dev/null 2>&1 && cp ../out/assemble.txt ../docs/assemble.txt || { echo "ASSEMBLE FAILED"; exit 3; }
push assemble
python3 -u block_verify.py > ../docs/block_verify.txt 2>&1 || echo "VERIFY rc=$? (see docs/block_verify.txt; a GATE FAILED line means nothing below it counts)"
push verify
echo "ALL DONE"

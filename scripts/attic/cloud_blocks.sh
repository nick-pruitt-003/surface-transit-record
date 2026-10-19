#!/bin/bash
# Cloud job: six-block tables, assembler over every block order, router re-check of the top 30. Results in docs/.
cd "$(dirname "$0")/.."   # run from scripts/: the live modules and ../out are relative to it
push () { git add ../docs/blocks_log.txt ../docs/assemble.txt ../docs/block_verify.txt 2>/dev/null; git commit -qm "cloud result: $1" || true; for i in 1 2 3; do git pull -q --rebase && git push -q && return 0; sleep 5; done; echo "PUSH FAILED $1" >&2; return 1; }
mkdir -p ../out
python3 -u blocks.py > ../docs/blocks_log.txt 2>&1 || { echo "BLOCKS FAILED"; push blocks-failed; exit 2; }
push blocks || exit 4
# assemble.py exits nonzero when calibration fails, and then writes no assemble.pkl for block_verify to read.
rm -f ../out/assemble.txt   # a run that fails before writing its report must not publish the previous one
python3 -u assemble.py > ../out/assemble.log 2>&1; rc=$?
cp ../out/assemble.txt ../docs/assemble.txt 2>/dev/null || cp ../out/assemble.log ../docs/assemble.txt
if [ $rc -ne 0 ]; then echo "ASSEMBLE FAILED rc=$rc"; push assemble-failed; exit 3; fi
push assemble || exit 4
python3 -u block_verify.py > ../docs/block_verify.txt 2>&1; rc=$?
if [ $rc -ne 0 ]; then echo "VERIFY FAILED rc=$rc (see docs/block_verify.txt)"; push verify-failed; exit $rc; fi
push verify || exit 4
echo "ALL DONE"

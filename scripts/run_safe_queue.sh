#!/bin/zsh
# ONE search at a time, 4 workers (the 4 performance cores), low priority. 8 GB machine: never run two.
LOCK=/Users/nick_pruitt/Downloads/bus48/out/.search.lock
if [ -e $LOCK ] && kill -0 $(cat $LOCK) 2>/dev/null; then echo "another queue is running (pid $(cat $LOCK))"; exit 1; fi
echo $$ > $LOCK; trap "rm -f $LOCK" EXIT
PY=/opt/homebrew/bin/python3
cd /Users/nick_pruitt/Downloads/bus48/scripts
export BUS48_MIN_TRANSFER=5 BUS48_WALKIN_KM=1.4
S=../out/resume_summary.txt
one() { # name, then time_search args
  n=$1; shift
  nice -n 10 $PY -u time_search.py "$@" --budget 900 --workers 4 --days 16 --out ../out/res_$n.pkl > ../out/res_$n.log 2>&1
  echo "$n: $(grep -E '^FINAL' ../out/res_$n.log)" >> $S
}
one kcdirect --start "Huntington Bus Stop" --at 2026-09-24T00:30 --tz America/New_York --seed-states "KY,OH,IN,IL,MO,IA,NE,SD,ND,MN,WI,MT,WA,OR,ID,UT,NV,CA,AZ,NM,CO,KS,OK,TX,AR,TN,MS,LA,AL,FL,GA,SC,NC,VA,MD,DE,PA,NJ,NY,CT,RI,MA,ME,NH,VT"
one record2 --start "White River Junction Bus Station" --at 2026-09-24T04:20 --tz America/New_York --seed ../out/time_238.pkl
one reverseA --start "White River Junction Bus Station" --at 2026-09-24T04:20 --tz America/New_York --seed-states "NH,ME,MA,RI,CT,NY,NJ,PA,DE,MD,VA,NC,SC,GA,FL,AL,LA,TX,OK,KS,CO,NM,AZ,CA,NV,UT,ID,OR,WA,MT,WY,MN,WI,ND,SD,NE,IA,MO,AR,MS,TN,KY,IL,IN,MI,OH,WV"
echo "queue: done" >> $S

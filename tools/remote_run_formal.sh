#!/usr/bin/env bash
# Run the Hyphae formal BMCs on the build box. Intended to be invoked under
# tmux (survives disconnects): tmux new -d -s formal 'bash ~/bin/run_formal.sh'
set -u
source /home/build/.neuro_env
cd /home/build/celiumneur/verification/formal
{
  echo "=== $(date -Is) fifo bmc"
  sby -f hypha_link_fifo.sby 2>&1 | tail -3
  echo "=== $(date -Is) router bmc"
  sby -f hypha_router.sby 2>&1 | tail -3
  echo "=== $(date -Is) done"
} >> /home/build/formal.log 2>&1
echo FORMAL_DONE >> /home/build/formal.log

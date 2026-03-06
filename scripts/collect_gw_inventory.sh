#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash scripts/collect_gw_inventory.sh <ssh_host> <remote_gw_dir>
# Example:
#   bash scripts/collect_gw_inventory.sh ks_ghj_3 ~/gw

host="${1:-}"
remote_dir="${2:-}"

if [[ -z "$host" || -z "$remote_dir" ]]; then
  echo "Usage: $0 <ssh_host> <remote_gw_dir>" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
out_dir="$repo_root/data"
mkdir -p "$out_dir/param-snapshots"

timestamp="$(date +%Y%m%d-%H%M%S)"
index_file="$out_dir/gw-index-$timestamp.tsv"
param_file="$out_dir/param-snapshots/params-$timestamp.txt"

ssh -o BatchMode=yes -o ConnectTimeout=10 "$host" "
set -e
cd $remote_dir
printf 'path\ttype\n'
find . -maxdepth 3 -type d | sed '1d' | while read -r d; do
  if [ -f \"\$d/librpa.in\" ]; then
    printf '%s\tGW_CASE\n' \"\$d\"
  elif [ -f \"\$d/INPUT_scf\" ] || [ -f \"\$d/INPUT_nscf\" ]; then
    printf '%s\tABACUS_CASE\n' \"\$d\"
  fi
done
" > "$index_file"

ssh -o BatchMode=yes -o ConnectTimeout=10 "$host" "
set -e
cd $remote_dir
find . -maxdepth 4 -type f \( -name 'librpa.in' -o -name 'INPUT_scf' -o -name 'INPUT_nscf' \) | while read -r f; do
  echo '===== '"'$remote_dir'"'/'\"\$f\"' ====='
  grep -E '^(nbands|nfreq|use_shrink_abfs|rpa|exx_pca_threshold|shrink_abfs_pca_thr|shrink_lu_inv_thr|cs_inv_thr)[[:space:]]*' \"\$f\" || true
  echo
 done
" > "$param_file"

echo "DONE"
echo "- index: $index_file"
echo "- params: $param_file"

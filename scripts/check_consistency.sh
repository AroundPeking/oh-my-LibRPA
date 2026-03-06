#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/check_consistency.sh <case_dir>

case_dir="${1:-}"
if [[ -z "$case_dir" ]]; then
  echo "Usage: $0 <case_dir>" >&2
  exit 2
fi

scf="$case_dir/INPUT_scf"
nscf="$case_dir/INPUT_nscf"
librpa="$case_dir/librpa.in"

for f in "$scf" "$nscf" "$librpa"; do
  [[ -f "$f" ]] || { echo "Missing file: $f" >&2; exit 2; }
done

get_value() {
  local file="$1"
  local key="$2"
  awk -v k="$key" '
    BEGIN{IGNORECASE=1}
    {
      line=$0
      gsub(/^[ \t]+/,"",line)
      if (line ~ ("^"k"([ \t=]|$)")) {
        v=line
        sub("^"k"[ \t]*=?[ \t]*","",v)
        gsub(/[ \t]+$/,"",v)
        print v
      }
    }
  ' "$file" | tail -n1
}

nb_scf=$(get_value "$scf" "nbands" || true)
nb_nscf=$(get_value "$nscf" "nbands" || true)

if [[ -z "$nb_scf" || -z "$nb_nscf" ]]; then
  echo "WARN: nbands not found in one of INPUT files"
else
  if [[ "$nb_scf" != "$nb_nscf" ]]; then
    echo "FAIL: nbands mismatch: SCF=$nb_scf NSCF=$nb_nscf" >&2
    exit 1
  fi
  echo "PASS: nbands consistent: $nb_scf"
fi

nfreq=$(get_value "$librpa" "nfreq" || true)
if [[ -z "$nfreq" ]]; then
  echo "WARN: nfreq not found in librpa.in"
elif [[ "$nfreq" != "16" ]]; then
  echo "WARN: nfreq=$nfreq (recommended smoke default: 16)"
else
  echo "PASS: nfreq=16 smoke default"
fi

if grep -qiE '^use_shrink_abfs[[:space:]]*=[[:space:]]*t' "$librpa"; then
  for key in rpa exx_pca_threshold shrink_abfs_pca_thr shrink_lu_inv_thr cs_inv_thr; do
    if ! grep -qE "^$key[[:space:]]+" "$scf"; then
      echo "FAIL: use_shrink_abfs=t but missing $key in INPUT_scf" >&2
      exit 1
    fi
  done
  echo "PASS: shrink_abfs coupling parameters found"

  val_exx=$(get_value "$scf" "exx_pca_threshold" || true)
  val_lu=$(get_value "$scf" "shrink_lu_inv_thr" || true)
  val_cs=$(get_value "$scf" "cs_inv_thr" || true)

  [[ "$val_exx" == "10" ]] || echo "WARN: exx_pca_threshold=$val_exx (common default: 10)"
  [[ "$val_lu" == "1e-3" ]] || echo "WARN: shrink_lu_inv_thr=$val_lu (common default: 1e-3)"
  [[ "$val_cs" == "1e-5" ]] || echo "WARN: cs_inv_thr=$val_cs (common default: 1e-5)"
fi

echo "DONE: static checks passed"

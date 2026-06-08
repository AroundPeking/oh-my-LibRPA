#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  check_consistency.sh <case_dir> [--mode <auto|gw|rpa>] [--system-type <auto|molecule|solid|2D>]

Behavior:
  - Validates only the files required by the selected route
  - Infers `mode` from `librpa.in: task` when `--mode auto`
  - Infers `system_type` from KPT files when `--system-type auto`
EOF
}

note_pass() {
  echo "PASS: $*"
  pass_count=$((pass_count + 1))
}

note_warn() {
  echo "WARN: $*"
  warn_count=$((warn_count + 1))
}

note_fail() {
  echo "FAIL: $*" >&2
  fail_count=$((fail_count + 1))
}

get_value() {
  local file="$1"
  local key="$2"
  awk -v k="$key" '
    BEGIN { IGNORECASE = 1 }
    {
      line = $0
      gsub(/^[ \t]+/, "", line)
      if (line ~ ("^" k "([ \t=]|$)")) {
        value = line
        sub("^" k "[ \t]*=?[ \t]*", "", value)
        gsub(/[ \t]+$/, "", value)
        print value
      }
    }
  ' "$file" | tail -n 1
}

lower() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

trim() {
  printf '%s' "$1" | awk '{ gsub(/^[ \t]+|[ \t]+$/, "", $0); print }'
}

detect_kpt_triplet() {
  local file="$1"
  [[ -f "$file" ]] || return 1
  awk '
    /^[[:space:]]*#/ { next }
    NF >= 3 && $1 ~ /^[-+0-9.]+$/ && $2 ~ /^[-+0-9.]+$/ && $3 ~ /^[-+0-9.]+$/ {
      print $1 " " $2 " " $3
      exit
    }
  ' "$file"
}

has_key_value() {
  local file="$1"
  local key="$2"
  local expected="$3"
  local value
  value="$(trim "$(get_value "$file" "$key" || true)")"
  [[ "$value" == "$expected" ]]
}

has_active_key() {
  local file="$1"
  local key="$2"
  grep -qiE "^[[:space:]]*${key}([[:space:]=]|$)" "$file"
}

case_has_matching_files() {
  local root="$1"
  local pattern="$2"
  find "$root" -maxdepth 1 -type f -name "$pattern" | grep -q .
}

extract_stru_section_entries() {
  local file="$1"
  local section="$2"
  awk -v section="$section" '
    function trim_text(s) {
      gsub(/^[ \t]+|[ \t]+$/, "", s)
      return s
    }
    {
      line = $0
      sub(/#.*/, "", line)
      sub(/\/\/.*/, "", line)
      line = trim_text(line)
      if (capture) {
        if (line == "") {
          exit
        }
        if (line ~ /^[A-Z][A-Z0-9_]*$/) {
          exit
        }
        print line
      } else if (line == section) {
        capture = 1
      }
    }
  ' "$file"
}

resolve_case_path() {
  local root="$1"
  local entry="$2"
  if [[ "$entry" = /* ]]; then
    printf '%s\n' "$entry"
  else
    printf '%s\n' "$root/$entry"
  fi
}

extract_header_value() {
  local file="$1"
  local prefix="$2"
  awk -v prefix="$prefix" '
    function trim_text(s) {
      gsub(/^[ \t]+|[ \t]+$/, "", s)
      return s
    }
    {
      line = trim_text($0)
      if (index(line, prefix) == 1) {
        value = line
        sub("^" prefix "[ \t]*", "", value)
        print trim_text(value)
        exit
      }
    }
  ' "$file"
}

extract_header_count() {
  local file="$1"
  local label="$2"
  awk -v label="$label" '
    function trim_text(s) {
      gsub(/^[ \t]+|[ \t]+$/, "", s)
      return s
    }
    {
      line = trim_text($0)
      if (line ~ ("^Number of " label "(-->)?")) {
        print $NF
        exit
      }
    }
  ' "$file"
}

float_equal() {
  local left="$1"
  local right="$2"
  local tol="${3:-1e-6}"
  awk -v left="$left" -v right="$right" -v tol="$tol" '
    BEGIN {
      diff = left - right
      if (diff < 0) {
        diff = -diff
      }
      exit !(diff <= tol)
    }
  '
}

validate_abfs_assets() {
  local stru_file="$1"
  local root_dir="$2"

  local -a species_order=()
  local -a orb_entries=()
  local -a abfs_entries=()
  local idx=0

  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    species_order+=("$line")
  done < <(extract_stru_section_entries "$stru_file" "ATOMIC_SPECIES" | awk '{ print $1 }')

  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    orb_entries+=("$line")
  done < <(extract_stru_section_entries "$stru_file" "NUMERICAL_ORBITAL")

  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    abfs_entries+=("$line")
  done < <(extract_stru_section_entries "$stru_file" "ABFS_ORBITAL")

  if [[ "${#species_order[@]}" -eq 0 ]]; then
    note_fail "Could not parse ATOMIC_SPECIES from STRU while validating ABFS assets"
    return
  fi

  if [[ "${#orb_entries[@]}" -ne "${#species_order[@]}" ]]; then
    note_fail "NUMERICAL_ORBITAL count (${#orb_entries[@]}) does not match ATOMIC_SPECIES count (${#species_order[@]})"
    return
  fi

  if [[ "${#abfs_entries[@]}" -ne "${#species_order[@]}" ]]; then
    note_fail "ABFS_ORBITAL count (${#abfs_entries[@]}) does not match ATOMIC_SPECIES count (${#species_order[@]})"
    return
  fi

  for idx in "${!species_order[@]}"; do
    local species="${species_order[$idx]}"
    local orb_path
    local abfs_path
    local orb_element
    local abfs_element
    local orb_radius
    local abfs_radius
    local orb_f
    local abfs_f
    local abfs_g

    orb_path="$(resolve_case_path "$root_dir" "${orb_entries[$idx]}")"
    abfs_path="$(resolve_case_path "$root_dir" "${abfs_entries[$idx]}")"

    if [[ ! -f "$orb_path" ]]; then
      note_fail "Missing NUMERICAL_ORBITAL file for $species: $orb_path"
      continue
    fi
    if [[ ! -f "$abfs_path" ]]; then
      note_fail "Missing ABFS_ORBITAL file for $species: $abfs_path"
      continue
    fi

    orb_element="$(extract_header_value "$orb_path" "Element" || true)"
    abfs_element="$(extract_header_value "$abfs_path" "Element" || true)"
    if [[ -n "$orb_element" && "$orb_element" != "$species" ]]; then
      note_fail "NUMERICAL_ORBITAL element mismatch for $species: header says $orb_element in $(basename "$orb_path")"
    fi
    if [[ -n "$abfs_element" && "$abfs_element" != "$species" ]]; then
      note_fail "ABFS_ORBITAL element mismatch for $species: header says $abfs_element in $(basename "$abfs_path")"
    fi

    orb_radius="$(extract_header_value "$orb_path" "Radius Cutoff(a.u.)" || true)"
    abfs_radius="$(extract_header_value "$abfs_path" "Radius Cutoff(a.u.)" || true)"
    if [[ -n "$orb_radius" && -n "$abfs_radius" ]]; then
      if float_equal "$orb_radius" "$abfs_radius" 1e-6; then
        note_pass "ABFS radius matches NUMERICAL_ORBITAL for $species: $abfs_radius a.u."
      else
        note_fail "ABFS radius mismatch for $species: orb=$orb_radius a.u. abfs=$abfs_radius a.u."
      fi
    else
      note_warn "Could not read both orbital radii for $species while validating ABFS assets"
    fi

    orb_f="$(extract_header_count "$orb_path" "Forbital" || true)"
    abfs_f="$(extract_header_count "$abfs_path" "Forbital" || true)"
    abfs_g="$(extract_header_count "$abfs_path" "Gorbital" || true)"
    if [[ "$orb_f" =~ ^[0-9]+$ ]] && (( orb_f > 0 )); then
      if [[ "$abfs_f" =~ ^[0-9]+$ ]] && (( abfs_f > 0 )); then
        note_pass "ABFS keeps nonzero f channel for $species"
      else
        note_fail "ABFS is missing a nonzero f channel for $species even though the paired orbital contains f"
      fi

      if [[ "$abfs_g" =~ ^[0-9]+$ ]] && (( abfs_g > 0 )); then
        note_pass "ABFS keeps nonzero g channel for $species"
      else
        note_fail "ABFS is missing a nonzero g channel for $species even though the paired orbital contains f"
      fi
    fi
  done
}

case_dir=""
mode="auto"
system_type="auto"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) mode="$2"; shift 2 ;;
    --system-type) system_type="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --*)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -z "$case_dir" ]]; then
        case_dir="$1"
        shift
      else
        echo "Unexpected positional argument: $1" >&2
        usage >&2
        exit 2
      fi
      ;;
  esac
done

if [[ -z "$case_dir" ]]; then
  usage >&2
  exit 2
fi

scf="$case_dir/INPUT_scf"
nscf="$case_dir/INPUT_nscf"
librpa="$case_dir/librpa.in"
stru="$case_dir/STRU"
kpt="$case_dir/KPT"
kpt_scf="$case_dir/KPT_scf"
kpt_nscf="$case_dir/KPT_nscf"
input_main="$case_dir/INPUT"

pass_count=0
warn_count=0
fail_count=0

[[ -f "$scf" ]] || note_fail "Missing file: $scf"
[[ -f "$librpa" ]] || note_fail "Missing file: $librpa"

if [[ ! -f "$scf" || ! -f "$librpa" ]]; then
  echo "SUMMARY: pass=$pass_count warn=$warn_count fail=$fail_count"
  exit 1
fi

task_value="$(lower "$(trim "$(get_value "$librpa" "task" || true)")")"

resolved_mode="$mode"
if [[ "$resolved_mode" == "auto" ]]; then
  case "$task_value" in
    g0w0_band) resolved_mode="gw" ;;
    rpa) resolved_mode="rpa" ;;
    *) resolved_mode="unknown" ;;
  esac
fi

resolved_system_type="$system_type"
if [[ "$resolved_system_type" == "auto" ]]; then
  triplet="$(detect_kpt_triplet "$kpt" || detect_kpt_triplet "$kpt_scf" || true)"
  if [[ "$triplet" == "1 1 1" ]]; then
    resolved_system_type="molecule"
  elif [[ -f "$kpt_nscf" || -f "$nscf" ]]; then
    resolved_system_type="solid"
  else
    resolved_system_type="unknown"
  fi
fi

echo "INFO: mode=$resolved_mode system_type=$resolved_system_type"

if [[ "$resolved_mode" == "gw" ]]; then
  for input_file in "$scf" "$nscf" "$input_main"; do
    [[ -f "$input_file" ]] || continue

    if has_key_value "$input_file" "latname" "user_defined_lattice"; then
      note_pass "$(basename "$input_file") keeps latname = user_defined_lattice"
    else
      note_warn "$(basename "$input_file") does not set latname = user_defined_lattice; only required when the route explicitly depends on that merged-branch lattice handling"
    fi

    if grep -qiE '^[[:space:]]*exx_use_ewald([[:space:]]|$)' "$input_file"; then
      note_fail "$(basename "$input_file") still contains deprecated key exx_use_ewald"
    fi

    if grep -qiE '^[[:space:]]*cs_inv_thr([[:space:]]|$)' "$input_file"; then
      note_fail "$(basename "$input_file") still contains deprecated key cs_inv_thr; use exx_cs_inv_thr"
    fi

    if grep -qiE '^[[:space:]]*exx_spencer_type([[:space:]=]|$)' "$input_file"; then
      note_fail "$(basename "$input_file") still contains deprecated key exx_spencer_type"
    fi

    if grep -qiE '^[[:space:]]*out_bandgap([[:space:]=]|$)' "$input_file"; then
      note_fail "$(basename "$input_file") still contains invalid key out_bandgap"
    fi

    if has_key_value "$input_file" "rpa" "1"; then
      if has_key_value "$input_file" "exx_singularity_correction" "massidda"; then
        note_pass "$(basename "$input_file") keeps exx_singularity_correction = massidda for rpa 1"
      else
        note_fail "$(basename "$input_file") sets rpa 1 but is missing 'exx_singularity_correction massidda'"
      fi
    fi
  done

  helper_get_diel="$case_dir/get_diel.py"
  helper_output_librpa="$case_dir/output_librpa.py"
  helper_perform="$case_dir/perform.sh"
  if [[ -f "$helper_get_diel" ]]; then
    if grep -q "E_FERMI" "$helper_get_diel" && grep -q "EFERMI" "$helper_get_diel"; then
      note_pass "get_diel.py accepts both E_FERMI and legacy EFERMI"
    else
      note_fail "get_diel.py should accept both E_FERMI and legacy EFERMI for the merged ABACUS branch"
    fi
  fi

  if [[ -f "$helper_get_diel" || -f "$helper_perform" ]]; then
    if [[ -f "$helper_output_librpa" ]]; then
      note_pass "GW helper quartet includes output_librpa.py"
    else
      note_fail "GW periodic helper bundle is incomplete: get_diel.py/perform.sh requires output_librpa.py in the same case directory"
    fi
  fi

  helper_preprocess="$case_dir/preprocess_abacus_for_librpa_band.py"
  if [[ -f "$helper_preprocess" ]]; then
    if grep -q "resolve_wfc_file" "$helper_preprocess" && grep -q "KPT.info" "$helper_preprocess" && grep -q "wfk" "$helper_preprocess"; then
      note_pass "preprocess_abacus_for_librpa_band.py matches the merged-branch wavefunction output conventions"
    else
      note_fail "preprocess_abacus_for_librpa_band.py should resolve the merged-branch wavefunction filename variants"
    fi
  fi

  if has_key_value "$scf" "out_librpa_reader_version" "1"; then
    note_pass "INPUT_scf enables ABACUS LibRPA reader-v1 producer output"
  else
    note_fail "GW route requires 'out_librpa_reader_version 1' in INPUT_scf for ABACUS master_ghj reader-v1 outputs"
  fi

  if has_key_value "$librpa" "version_coul_reader" "1" && has_key_value "$librpa" "version_lri_reader" "1"; then
    note_pass "librpa.in selects reader-v1 for Coulomb and LRI data"
  else
    note_fail "GW route requires version_coul_reader = 1 and version_lri_reader = 1 in librpa.in"
  fi

  if has_key_value "$librpa" "prefix_coul_full" "v1_coulomb_full_iq_" \
     && has_key_value "$librpa" "prefix_coul_cut" "v1_coulomb_cut_iq_" \
     && has_key_value "$librpa" "prefix_lri_coeff" "v1_Cs_data_"; then
    note_pass "librpa.in uses ABACUS reader-v1 file prefixes"
  else
    note_fail "GW route requires prefix_coul_full = v1_coulomb_full_iq_, prefix_coul_cut = v1_coulomb_cut_iq_, and prefix_lri_coeff = v1_Cs_data_"
  fi

  if ! grep -qiE '^use_shrink_abfs[[:space:]]*=[[:space:]]*t([[:space:]]|$)' "$librpa" \
     || has_key_value "$librpa" "prefix_lri_coeff_shrink" "v1_Cs_data_"; then
    note_pass "librpa.in keeps reader-v1 LRI prefix synchronized on the shrink route"
  else
    note_fail "GW shrink route requires prefix_lri_coeff_shrink = v1_Cs_data_ with ABACUS reader-v1 outputs"
  fi

  if has_key_value "$librpa" "use_cholesky_gw_wc" "t"; then
    note_pass "librpa.in enables use_cholesky_gw_wc = t"
  else
    note_fail "GW route requires use_cholesky_gw_wc = t by default"
  fi

  if has_key_value "$librpa" "use_elpa_sqrt_coulomb" "t"; then
    note_pass "librpa.in enables use_elpa_sqrt_coulomb = t"
  else
    note_fail "GW route requires use_elpa_sqrt_coulomb = t by default"
  fi

  if has_key_value "$librpa" "use_kpara_scf_eigvec" "t"; then
    note_pass "librpa.in enables use_kpara_scf_eigvec = t"
  else
    note_fail "GW route requires use_kpara_scf_eigvec = t for the ABACUS reader-v1 eigenvector path"
  fi

  if has_key_value "$librpa" "libri_chi0_collect_max_bytes" "2147483648"; then
    note_pass "librpa.in sets libri_chi0_collect_max_bytes = 2147483648"
  else
    note_fail "GW route requires libri_chi0_collect_max_bytes = 2147483648 by default"
  fi
fi

case "$resolved_mode" in
  gw)
    [[ "$task_value" == "g0w0_band" ]] || note_fail "GW route expects 'task = g0w0_band' in librpa.in"
    ;;
  rpa)
    [[ "$task_value" == "rpa" ]] || note_fail "RPA route expects 'task = rpa' in librpa.in"
    ;;
  *)
    note_warn "Could not infer workflow mode from librpa.in; pass --mode explicitly if needed"
    ;;
esac

needs_periodic_gw_route=0
if [[ "$resolved_mode" == "gw" && "$resolved_system_type" != "molecule" ]]; then
  needs_periodic_gw_route=1
fi

if [[ "$needs_periodic_gw_route" -eq 1 ]]; then
  [[ -f "$nscf" ]] || note_fail "GW periodic route requires INPUT_nscf"
  [[ -f "$kpt_nscf" ]] || note_fail "GW periodic route requires KPT_nscf"
else
  [[ -f "$nscf" ]] || note_warn "INPUT_nscf not present; this is fine for RPA and molecular GW routes"
fi

nb_scf="$(trim "$(get_value "$scf" "nbands" || true)")"
nb_nscf=""
if [[ -f "$nscf" ]]; then
  nb_nscf="$(trim "$(get_value "$nscf" "nbands" || true)")"
fi
if [[ "$needs_periodic_gw_route" -eq 1 ]]; then
  if [[ -z "$nb_scf" || -z "$nb_nscf" ]]; then
    note_fail "GW periodic route requires nbands in both INPUT_scf and INPUT_nscf"
  elif [[ "$nb_scf" != "$nb_nscf" ]]; then
    note_fail "nbands mismatch: SCF=$nb_scf NSCF=$nb_nscf"
  else
    note_pass "nbands consistent across SCF and NSCF: $nb_scf"
  fi
elif [[ -n "$nb_scf" ]]; then
  note_pass "INPUT_scf defines nbands: $nb_scf"
else
  note_warn "nbands not found in INPUT_scf"
fi

nfreq="$(trim "$(get_value "$librpa" "nfreq" || true)")"
tfgrid_type="$(trim "$(get_value "$librpa" "tfgrid_type" || true)")"
if [[ -z "$tfgrid_type" ]]; then
  tfgrid_type="minimax"
fi
if [[ -z "$nfreq" ]]; then
  note_warn "nfreq not found in librpa.in"
elif [[ "$tfgrid_type" == "minimax" ]] && [[ "$nfreq" =~ ^[0-9]+$ ]] && (( nfreq < 6 )); then
  note_fail "tfgrid_type=minimax requires nfreq>=6 in LibRPA; nfreq=$nfreq is only acceptable with an explicit non-minimax grid such as evenspaced_tf"
elif [[ "$nfreq" == "16" ]]; then
  note_pass "nfreq=16 smoke default"
else
  note_warn "nfreq=$nfreq (recommended smoke default: 16)"
fi

if grep -qiE '^use_shrink_abfs[[:space:]]*=[[:space:]]*t([[:space:]]|$)' "$librpa"; then
  for key in rpa exx_pca_threshold shrink_abfs_pca_thr shrink_lu_inv_thr exx_cs_inv_thr; do
    if grep -qiE "^${key}[[:space:]]+" "$scf"; then
      note_pass "shrink companion key present in INPUT_scf: $key"
    else
      note_fail "use_shrink_abfs=t but missing $key in INPUT_scf"
    fi
  done

  val_exx="$(trim "$(get_value "$scf" "exx_pca_threshold" || true)")"
  val_lu="$(trim "$(get_value "$scf" "shrink_lu_inv_thr" || true)")"
  val_cs="$(trim "$(get_value "$scf" "exx_cs_inv_thr" || true)")"
  [[ "$val_exx" == "10" ]] || note_warn "exx_pca_threshold=$val_exx (common default: 10)"
  [[ "$val_lu" == "1e-3" ]] || note_warn "shrink_lu_inv_thr=$val_lu (common default: 1e-3)"
  [[ "$val_cs" == "1e-5" ]] || note_warn "exx_cs_inv_thr=$val_cs (common default: 1e-5)"

  if [[ -f "$stru" ]]; then
    if grep -qiE '^[[:space:]]*ABFS_ORBITAL([[:space:]]|$)' "$stru"; then
      note_pass "STRU contains ABFS_ORBITAL for shrink route"
      validate_abfs_assets "$stru" "$case_dir"
    else
      note_fail "use_shrink_abfs=t but STRU is missing ABFS_ORBITAL"
    fi
  else
    note_warn "STRU not found; could not verify ABFS_ORBITAL for shrink route"
  fi

  if has_active_key "$scf" "shrink_abfs_pca_thr" || has_active_key "$scf" "shrink_lu_inv_thr" \
     || case_has_matching_files "$case_dir" 'shrink_sinvS_*' \
     || case_has_matching_files "$case_dir" 'Cs_shrinked_data_*'; then
    note_pass "ABACUS-side bundle shows shrink markers/artifacts consistent with use_shrink_abfs=t"
  else
    note_fail "use_shrink_abfs=t but the bundle does not show shrink markers/artifacts from ABACUS"
  fi
elif grep -qiE '^use_shrink_abfs[[:space:]]*=[[:space:]]*f([[:space:]]|$)' "$librpa"; then
  if has_active_key "$scf" "shrink_abfs_pca_thr"; then
    note_fail "use_shrink_abfs=f but INPUT_scf still contains shrink_abfs_pca_thr"
  else
    note_pass "no-shrink lane keeps shrink_abfs_pca_thr out of INPUT_scf"
  fi

  if has_active_key "$scf" "shrink_lu_inv_thr"; then
    note_fail "use_shrink_abfs=f but INPUT_scf still contains shrink_lu_inv_thr"
  else
    note_pass "no-shrink lane keeps shrink_lu_inv_thr out of INPUT_scf"
  fi

  if case_has_matching_files "$case_dir" 'shrink_sinvS_*' \
     || case_has_matching_files "$case_dir" 'Cs_shrinked_data_*'; then
    note_fail "use_shrink_abfs=f but the bundle still contains shrink artifacts (shrink_sinvS_* or Cs_shrinked_data_*)"
  else
    note_pass "no-shrink lane does not carry shrink artifacts from ABACUS"
  fi

  if [[ -f "$stru" ]] && grep -qiE '^[[:space:]]*ABFS_ORBITAL([[:space:]]|$)' "$stru"; then
    note_warn "STRU contains ABFS_ORBITAL while use_shrink_abfs=f; confirm this is intentional and not a mixed shrink/no-shrink lane"
  fi
fi

if grep -qiE '^use_pair_embedding_corr[[:space:]]*=[[:space:]]*t([[:space:]]|$)' "$librpa"; then
  if has_key_value "$scf" "out_pair_embedding_metric" "1"; then
    note_pass "pair-correction lane enables out_pair_embedding_metric = 1 in INPUT_scf"
  else
    note_fail "use_pair_embedding_corr=t but INPUT_scf is missing 'out_pair_embedding_metric 1'"
  fi

  scf_pair_cut="$(trim "$(get_value "$scf" "pair_embedding_distance_cut" || true)")"
  librpa_pair_cut="$(trim "$(get_value "$librpa" "pair_embedding_distance_cut" || true)")"
  if [[ -z "$scf_pair_cut" || -z "$librpa_pair_cut" ]]; then
    note_fail "pair-correction lane requires pair_embedding_distance_cut in both INPUT_scf and librpa.in"
  elif [[ "$scf_pair_cut" != "$librpa_pair_cut" ]]; then
    note_fail "pair_embedding_distance_cut mismatch: INPUT_scf=$scf_pair_cut librpa.in=$librpa_pair_cut"
  else
    note_pass "pair_embedding_distance_cut consistent across ABACUS and LibRPA: $scf_pair_cut"
  fi

  if has_active_key "$librpa" "pair_embedding_metric_thr"; then
    note_pass "librpa.in defines pair_embedding_metric_thr"
  else
    note_fail "use_pair_embedding_corr=t but librpa.in is missing pair_embedding_metric_thr"
  fi
fi

if [[ "$resolved_mode" == "gw" && "$resolved_system_type" == "molecule" ]]; then
  triplet="$(detect_kpt_triplet "$kpt" || detect_kpt_triplet "$kpt_scf" || true)"
  if [[ "$triplet" == "1 1 1" ]]; then
    note_pass "molecular GW route uses KPT=1 1 1"
  else
    note_fail "molecular GW route requires KPT=1 1 1"
  fi

  if has_key_value "$scf" "out_mat_xc" "1"; then
    note_pass "molecular GW route keeps out_mat_xc = 1"
  else
    note_fail "molecular GW route requires 'out_mat_xc 1' in INPUT_scf"
  fi

  if has_key_value "$scf" "exx_singularity_correction" "massidda"; then
    note_pass "molecular GW route keeps exx_singularity_correction = massidda"
  else
    note_fail "molecular GW route requires 'exx_singularity_correction massidda' in INPUT_scf so Coulomb files are generated"
  fi

  exx_ccp="$(trim "$(get_value "$scf" "exx_ccp_rmesh_times" || true)")"
  rpa_ccp="$(trim "$(get_value "$scf" "rpa_ccp_rmesh_times" || true)")"
  if [[ -n "$exx_ccp" && -n "$rpa_ccp" && "$exx_ccp" == "$rpa_ccp" ]]; then
    note_pass "molecular GW route keeps exx_ccp_rmesh_times equal to rpa_ccp_rmesh_times"
  else
    note_fail "molecular GW route requires exx_ccp_rmesh_times and rpa_ccp_rmesh_times to match"
  fi

  if grep -qiE '^[[:space:]]*gamma_only[[:space:]]+1([[:space:]]|$)' "$scf"; then
    note_pass "gamma_only 1 is enabled for the molecular GW route"
  else
    note_warn "gamma_only is not enabled; keep it route-aware rather than treating it as a hard global rule"
  fi

  if grep -qiE '^[[:space:]]*out_chg[[:space:]]+1([[:space:]]|$)' "$scf"; then
    note_warn "out_chg is enabled even though the short molecular GW route does not need NSCF"
  fi

  if grep -qiE '^[[:space:]]*out_mat_r[[:space:]]+1([[:space:]]|$)' "$scf"; then
    note_warn "out_mat_r is enabled even though the no-pyatb molecular GW route does not need it"
  fi

  if grep -qiE '^[[:space:]]*out_mat_hs2[[:space:]]+1([[:space:]]|$)' "$scf"; then
    note_warn "out_mat_hs2 is enabled even though the no-pyatb molecular GW route does not need it"
  fi

  if has_key_value "$librpa" "replace_w_head" "f"; then
    note_pass "molecular GW route sets replace_w_head = f"
  else
    note_fail "molecular GW route requires 'replace_w_head = f' in librpa.in"
  fi

  if has_key_value "$librpa" "use_abacus_exx_symmetry" "f" && has_key_value "$librpa" "use_abacus_gw_symmetry" "f"; then
    note_pass "molecular GW route disables ABACUS symmetry flags in librpa.in"
  else
    note_fail "molecular GW route requires use_abacus_exx_symmetry = f and use_abacus_gw_symmetry = f in librpa.in"
  fi

  if has_key_value "$librpa" "use_shrink_abfs" "f"; then
    note_pass "molecular GW smoke route keeps use_shrink_abfs = f"
  else
    note_warn "use_shrink_abfs is not set to f; the tested molecular smoke route used no shrink"
  fi
fi

if [[ "$resolved_mode" == "rpa" ]]; then
  if grep -qiE '^[[:space:]]*option_dielect_func[[:space:]]*=[[:space:]]*3([[:space:]]|$)' "$librpa"; then
    note_warn "RPA route still contains GW-only setting option_dielect_func = 3"
  fi
  if grep -qiE '^[[:space:]]*output_gw_sigc_mat_rf[[:space:]]*=[[:space:]]*t([[:space:]]|$)' "$librpa"; then
    note_warn "RPA route still contains GW-only setting output_gw_sigc_mat_rf = t"
  fi
fi

echo "SUMMARY: pass=$pass_count warn=$warn_count fail=$fail_count"

if [[ "$fail_count" -gt 0 ]]; then
  exit 1
fi

echo "DONE: static checks passed"

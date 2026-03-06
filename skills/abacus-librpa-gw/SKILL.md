---
name: abacus-librpa-gw
description: ABACUS + LibRPA GW workflow guidance and static input checks. Use when planning, preparing, or validating GW runs, including SCF/DF/NSCF chaining, librpa.in consistency, and safe run-directory setup.
---

# ABACUS + LibRPA GW

执行顺序：`SCF -> DF(pyatb_librpa_df) -> NSCF -> LibRPA`。

## 必做检查

- 检查 `INPUT_scf` 与 `INPUT_nscf` 的 `nbands` 与体系基组规模一致
- 检查 `librpa.in` 与 ABACUS 输出目录来自同一流程
- 检查是否在新目录运行，避免旧输出残留污染

## 参数联动规则

若 `use_shrink_abfs = t`，必须校验配套参数是否齐全：

- `rpa 1`
- `exx_pca_threshold 10`
- `shrink_abfs_pca_thr 1e-4`
- `shrink_lu_inv_thr 1e-3`
- `cs_inv_thr 1e-5`

## 输出要求

每次给建议时都同时给出：

- 为什么这么改
- 风险是什么
- 如何用最小代价验证

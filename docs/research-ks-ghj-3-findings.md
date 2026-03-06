# ks_ghj_3 `~/gw` 样例采集结果（首轮）

## 采集信息

- 时间：2026-03-06 12:26 (GMT+8)
- 数据源：`ks_ghj_3:~/gw`
- 索引文件：`data/gw-index-20260306-122643.tsv`
- 参数快照：`data/param-snapshots/params-20260306-122643.txt`

## 样例规模

- 总条目（含表头）：278
- 实际案例：277
  - `GW_CASE`: 258
  - `ABACUS_CASE`: 19

说明：该目录主体是 GW 任务数据，符合 `oh-my-librpa` 首发聚焦 GW 的策略。

## 目录分布（Top）

按一级目录粗分（案例数）：

- `AlAs`: 31
- `shrink_test`: 26
- `reg_test`: 25
- `GaAs`: 22
- `MgO`: 19
- `abacus_input`: 15
- `CdS`: 15
- `nonlin_soc_gw`: 14

结论：`shrink_test/reg_test/nonlin_soc_gw` 非常适合优先提炼“参数联动 + 排错规则卡”。

## 关键参数分布（快照）

### `nfreq`

- 16（176 次）
- 6（22 次）
- 8（14 次）
- 24（13 次）

结论：`nfreq=16` 是最强主模态，可作为 smoke 默认值。

### `use_shrink_abfs`

- `t`（156 次）
- `f`（9 次）

结论：应把 shrink_abfs 路径作为默认流程，不应作为边缘分支处理。

### `rpa`

- `1`（208 次）

结论：与已有经验一致，可在检查器中作为强约束。

### 典型耦合阈值

- `exx_pca_threshold`: 10（367 次）
- `shrink_lu_inv_thr`: 1e-3（74 次）
- `cs_inv_thr`: 1e-5（51 次）
- `shrink_abfs_pca_thr`: 1e-6（92 次），其次 1e-4（14 次）

结论：`exx_pca_threshold=10` 与 `shrink_lu_inv_thr=1e-3`、`cs_inv_thr=1e-5` 可先作为推荐默认；`shrink_abfs_pca_thr` 需按体系再细分（1e-6 与 1e-4 并存）。

## 对 oh-my-librpa 的直接动作建议

1. 在 `check_consistency.sh` 中新增“建议等级”：
   - 强约束：`rpa=1`、耦合参数齐全
   - 建议项：`nfreq=16`（smoke）

2. 新增规则卡两类：
   - `shrink-abfs-default-lane`
   - `nfreq-smoke-ladder`（16 -> 24/32 的升级策略）

3. 下一轮采集聚焦：
   - `shrink_test/*`
   - `reg_test/*`
   - `nonlin_soc_gw/*`
   提取失败日志关键词（含 `stod`）并映射修复动作。

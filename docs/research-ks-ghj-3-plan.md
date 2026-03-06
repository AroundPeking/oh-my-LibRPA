# 数据源调研计划：ks_ghj_3 `~/gw`

## 当前状态

- 从当前机器直连 `ks_ghj_3 (10.254.253.3:22)` 超时。
- 通过 `Fisherd` 跳板也超时。

## 连通后要做的最小采集

1. 样例总览
   - 目录树深度 2~3
   - 按体系/任务类型分组（GW/RPA/EXX）

2. 输入参数抽样
   - `INPUT_scf` / `INPUT_nscf` / `librpa.in`
   - 统计关键参数分布（`nbands`, `nfreq`, `use_shrink_abfs`）

3. 失败案例索引
   - 搜集日志中的典型报错关键词（如 `stod`）

4. 规则卡生成
   - 从真实案例提炼规则卡（每条规则都附样例路径）

## 采集产物

- `data/gw-index.tsv`
- `data/param-snapshots/*.txt`
- `rules/cards/*.yml`（由样例归纳）

## 快速命令（连通后）

```bash
bash scripts/collect_gw_inventory.sh ks_ghj_3 ~/gw
```

---
name: abacus-librpa-rpa
description: ABACUS + LibRPA RPA workflow guidance with focus on dielectric setup, frequency grids, and convergence-oriented static checks. Use when preparing or troubleshooting RPA calculations.
---

# ABACUS + LibRPA RPA

优先目标：先得到稳定、可复现实验级别的 RPA 结果，再追求性能和规模。

## 建议流程

- 先用小体系 smoke case 验证输入链路
- 再逐步提高 `nfreq`、k 点与能带截断

## 静态检查清单

- 目录来源一致（同一套 SCF/NSCF 输出）
- 频率网格参数自洽
- 关键文件路径不跨目录拼接

## 输出要求

- 优先给“最小可行修复”
- 每次只改一个变量，减少耦合不确定性

---
name: abacus-librpa-debug
description: Diagnose ABACUS + LibRPA RPA/GW failures from logs and inputs. Use when runs fail, outputs are inconsistent, or there are parser/read errors such as stod issues.
---

# ABACUS + LibRPA Debug

先定位失败阶段，再给针对性修复，不做大范围盲改。

## 诊断顺序

1. 判定失败阶段：SCF / DF / NSCF / LibRPA
2. 检查输入来源是否混杂
3. 检查旧输出残留是否污染当前任务
4. 检查关键阈值参数是否缺项或冲突

## 常见问题

- `stod` 读取报错：优先检查输入格式和残留文件污染
- 结果异常跳变：优先检查 `nbands` 与基组规模关系

## 输出格式

- `症状`
- `最可能根因`
- `最小修复动作`
- `验证动作`

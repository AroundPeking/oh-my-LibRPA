# smoke-nii2

这个目录用于最小 smoke 测试样例。

建议流程：

1. 准备同一链路输出的 `INPUT_scf` / `INPUT_nscf` / `librpa.in`
2. 执行静态检查：
   - `bash ../../scripts/check_consistency.sh .`
3. 再决定是否提交远程小任务

约束：

- 必须新建目录运行
- 禁止覆盖原始数据目录

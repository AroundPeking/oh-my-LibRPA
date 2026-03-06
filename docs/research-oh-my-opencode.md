# 调研笔记：oh-my-opencode 可借鉴点

## 结论（可直接迁移到 oh-my-librpa）

1. **安装入口要“给 AI 看”的版本**
   - `oh-my-opencode` 的 README 直接给出可复制提示词与 `curl` 文档入口。
   - 对 `oh-my-librpa` 可做：`Install and configure oh-my-librpa by following ...`。

2. **“编排层”与“执行层”分离**
   - 它把“主控 agent（规划/分发）”与“子 agent（执行）”分开。
   - 对 `oh-my-librpa` 可做：
     - 编排层：选流程（GW/RPA/Debug）
     - 执行层：静态检查、参数生成、错误诊断

3. **按类别路由，而不是按模型硬编码**
   - 它使用 category 路由（quick/deep/visual...）。
   - 对 `oh-my-librpa` 可做：
     - `workflow-gw`
     - `workflow-rpa`
     - `diagnosis`
     - `literature-review`

4. **技能写法强调“可执行协议”**
   - 它的技能不是概念介绍，而是明确步骤、输入输出、失败分支。
   - 对 `oh-my-librpa`：SKILL.md 继续向“协议式”强化（症状->根因->修复->验证）。

5. **文档层级清晰**
   - `README`（入口）-> `guide`（操作）-> `reference`（细节）。
   - 对 `oh-my-librpa`：
     - `README.md`：定位与快速开始
     - `docs/guide/*.md`：流程指南
     - `references/*.md`：参数口径与术语

## 不建议照搬的点

- 高营销叙事风格不适合科研算例仓库。
- 通用多模型“炫技”不应优先于“结果可复现”。

## 对 oh-my-librpa 的具体落地动作

- 增加 `docs/guide/installation.md`（给 AI 的安装/初始化提示）。
- 增加 `docs/guide/workflow-gw.md` 与 `workflow-rpa.md`。
- 将规则卡统一为 YAML 协议字段：`scene/symptom/root_cause/fix/verify/applies_to`。
- 增加“最小 smoke 成功标准”，作为每个流程的退出条件。

# oh-my-librpa

`oh-my-librpa` 是一个面向 `ABACUS + LibRPA`（并可扩展到其他 DFT 软件）的 **对话优先（chat-first）** AI 经验层。

目标：用户只需要自然语言描述任务，AI 自动按经验完成 GW/RPA 的准备、检查、诊断与迭代。

## 一键安装（用户侧）

```bash
curl -fsSL https://raw.githubusercontent.com/AroundPeking/oh-my-LibRPA/main/install.sh | bash
```

开发态本地安装：

```bash
cd ~/code/oh-my-librpa
bash install.sh
```

安装后不需要记命令，直接对话：

- `帮我做 GaAs 的 GW，先稳妥跑通。`
- `这是分子体系，按分子路线准备输入。`
- `这个报错怎么修，给最小修复动作。`

## 当前范围（MVP）

- 对话编排技能：`oh-my-librpa`（统一入口）
- 核心工作技能：`abacus-librpa-gw` / `abacus-librpa-rpa` / `abacus-librpa-debug`
- 规则卡（经验结构化）：场景、症状、根因、修复、验证
- 模板库：`INPUT_scf`、`INPUT_nscf`、`librpa.in` 最小模板
- 静态检查脚本：输入一致性、目录安全约束

## 仓库结构

```text
oh-my-librpa/
├── skills/
│   ├── oh-my-librpa/
│   ├── abacus-librpa-gw/
│   ├── abacus-librpa-rpa/
│   └── abacus-librpa-debug/
├── references/
├── rules/cards/
├── templates/
├── scripts/
├── examples/
├── registry/
└── docs/
```

## 设计原则

- 对话优先：不要求用户记任何专用命令
- 分流执行：自动区分 `molecule` / `solid` / `2D`
- 经验驱动：规则卡优先于临时拍脑袋参数
- 安全约束：新目录运行，禁止覆盖原始数据

## 安全约束

- 默认先做静态分析，再决定是否提交远程任务
- 远程计算必须新建独立目录
- 禁止覆盖原始数据目录

# Chat Guidance: How to Use oh-my-LibRPA in Natural Language

This guide is for humans.

The point of `oh-my-librpa` is **not** to make you remember more commands.
The point is to let you say what you want in plain language, and let the agent fill in the workflow details safely.

---

## 1. What kinds of things you can say

Typical requests:

### GW

- `在 ks_ghj_3 服务器上做一个 Si 的 k444 的 GW 计算，目录用 ~/gw/Si/AI/。`
- `这是分子体系，先给我做一个保守 smoke。`
- `帮我在远端准备 GW 输入，但先不要提交。`
- `继续盯，直到成功。`

### RPA

- `给这个体系做一个 RPA smoke，先保守一点。`
- `先检查我这套 RPA 输入有没有明显不一致。`

### Debug

- `这个 GW 跑挂了，帮我定位是 SCF、pyatb、NSCF 还是 LibRPA 的问题。`
- `slurm 输出在这，帮我直接找根因。`

### Postprocessing

- `根据输出的 GW_band_spin_* 和能带路径画一个论文风格的能带图。`
- `把这次计算中遇到的问题、修法和建议总结成一份给开发者的文档。`

---

## 2. 一条“好用”的用户请求通常包含什么

不是每次都要全说全，但下面这些信息越明确，流程越顺。

### 对远程计算最重要的信息

1. **在哪台服务器上跑**
2. **在哪个目录里准备输入**
3. **这是分子、固体还是 2D 体系**
4. **是否已经把基组 / 辅助基 / 赝势 / `KPT_nscf` 放好了**
5. **是否允许直接提交**，还是先静态检查

### 对 periodic GW 最重要的信息

1. `KPT` 网格（例如 `4 4 4`）
2. `KPT_nscf` 是否已经准备好
3. 晶格常数 / 结构来源
4. 是否要先做 smoke

### 一个足够好的例子

```text
在 ks_ghj_3 服务器上做一个 Si 的 k444 GW 计算。
计算目录用 ~/gw/Si/AI/。
基组、辅助基、赝势和 KPT_nscf 都已经放在目录里了。
晶格常数用 5.431 Å。
先检查再提交。
```

---

## 3. agent 应该怎么回应你

一个靠谱的 agent 不应该一上来就开始猜。

它应该做的事通常是：

1. **确认远端可达**
2. **盘点输入文件**
3. **只问缺失的信息**
4. **新建 fresh run directory**
5. **先做 preflight / consistency check**
6. **把关键参数回报给你**
7. 在你同意后再提交
8. 每个阶段都给你一个短更新

### 好的阶段更新应该长这样

每次更新只要三件事：

- what was done
- what was observed
- what is next

而不是把整份长日志糊你脸上。

---

## 4. 一个真实案例：Si `k=4x4x4` periodic GW

完整案例见：

- `examples/si-k444-gw/README.md`

这里先给短版流程。

### 用户最初的请求

```text
在 ks_ghj_3 服务器上做一个 Si 的 k444 的 gw 计算，
计算目录使用 ~/gw/Si/AI/,
使用的基组、辅助基和赝势都在计算目录里面了，
Si 的晶格常数设为 5.431 埃
```

### agent 补问的关键点

只补问了真正缺的 3 个：

1. VPN 是否已登录
2. 是否允许新建 fresh 子目录
3. `KPT_nscf` 是否已在目录中

### 为什么这三个问题合理

因为它们分别决定：

- 能不能连上机器
- 会不会污染旧数据
- periodic GW 的 band-path 是否闭环

不是所有事情都值得问。
问太多，用户会烦。
不问关键点，流程会翻车。

---

## 5. 这类任务里，agent 最容易犯的错误

这是这次真实 case 暴露出来的。

### 错误 1：默认可执行文件路径一定对

不应该默认模板里的 `abacus` / `librpa` 路径一定有效。

更好的做法：

- 先问用户
- 或从 server profile 读取
- 或自动探测后回显确认

### 错误 2：默认 batch 环境等于 interactive shell

在 HPC 上，这经常是错的。

### 错误 3：默认 `python` 就是 `python3`

这在老机器上经常错得离谱。

### 错误 4：默认有 Slurm 就优先 `srun`

不一定。
有些环境里 `mpirun` 才是正确路。

### 错误 5：前面已经炸了，后面还继续跑

workflow 一定要 fail-fast。

---

## 6. 如果你想让 agent 更省心，建议你这么说

### 情况 A：你想让它先检查，不要急着提

```text
在 ks_ghj_3 上做一个 Si 的 k444 GW。
目录用 ~/gw/Si/AI/。
orb、abfs、upf 和 KPT_nscf 都在里面。
晶格常数 5.431 Å。
先做静态检查，把关键参数回我，再提交。
```

### 情况 B：你已经信任它，可以直接推进

```text
VPN 已登录。
可以新建子目录。
KPT_nscf 也在 ~/gw/Si/AI/ 下面。
按保守 smoke 跑，成功前继续盯。
```

### 情况 C：你想要后处理

```text
根据输出的 GW_band_spin_* 和能带路径用 python 画能带图，要求论文画风，清晰好看。
```

---

## 7. 画图这一步也应该是 chat-first 的

一个成熟的 `oh-my-librpa` 不应该把 plotting 当成仓库外的手工活。

用户完全可以直接说：

```text
把 GW_band_spin_* 画成论文风格的能带图。
```

agent 应该自动知道至少要去找：

- `GW_band_spin_*`
- `band_out`
- `band_kpath_info`
- `KPT_nscf`

并自动处理：

- VBM 对零点
- 高对称点标签
- 近带隙带的选择
- PNG / PDF 导出

---

## 8. 推荐的对话节奏

### 第 1 步：用户给任务

一句自然语言就够。

### 第 2 步：agent 只问关键缺口

最好不超过 2–5 个问题。

### 第 3 步：preflight

先静态检查，再提交。

### 第 4 步：阶段报告

SCF / pyatb / NSCF / preprocess / LibRPA。

### 第 5 步：收尾

成功后，顺手支持：

- 结果总结
- 图
- 给开发者的反馈文档

---

## 9. 如果你是开发者，应该把这份 guidance 放到哪里

这份 guidance 不应该只放在 README 里。

建议至少放 3 处：

1. `README.md`
   - 给第一次接触仓库的人看
2. `docs/guide/chat-guidance.md`
   - 给真正使用插件的人看
3. `rules/cards/`
   - 给 agent 保留结构化提问顺序和经验规则

换句话说：

- **README 解决“这是什么”**
- **guide 解决“我怎么说”**
- **rules 解决“agent 应该怎么做”**

---

## 10. 一句话版本

如果你只记一句：

> 把任务目标、服务器、目录、关键输入是否就位说清楚；剩下的流程细节应该由 `oh-my-librpa` 去补，而不是让用户手搓。 

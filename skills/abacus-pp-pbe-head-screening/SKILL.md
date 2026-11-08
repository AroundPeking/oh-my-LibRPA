---
name: abacus-pp-pbe-head-screening
description: Use when selecting GTH, SG15, or PseudoDojo pseudopotentials and matched TZDP orbitals for ABACUS plus LibRPA, auditing SIAB_INPUT and effective basis-generation parameters, or comparing PBE bands and FHI-aims all-electron response, including strict-2D materials.
---

# PBE 与全电子 head 联合筛选赝势

## 先查 LibRPA 数据库

元素资产的唯一来源是 LibRPA 数据库（`https://github.com/AroundPeking/LibRPA-database`），
通过 `librpa-database` MCP 服务器访问：

- `list_basis_sets(element=...)` —— 列出该元素所有已登记的 PP/NAO/ABFS/for_aux
  配套，每条带 payload 的 SHA-256；
- `search_materials(...)` —— 找出已经绑定某套配套的历史计算，新材料可以直接
  从老材料用过的配套起步；
- `get_material(record_id)` —— 拿到每个元素的精确 `set_id`。

PP/物理 NAO/原始 ABFS 按元素和完整哈希跨材料复用，不按材料重新生成；
例如 MoS2、MoSe2、MoTe2 应先查所有 Mo 的历史配套，而不是只查新材料名。
清单里没列出来不能作为缺失证据，要先按元素重新查询。
原来的本地库 `2d_gw_pp_basis_library` 与 `2d_gw/pp_basis_library` 已在
2026-11-05 退役：其中 263 个 PP/NAO/ABFS payload 逐个按哈希验证都已收录进
数据库，目录已删除，不要再指向它们。

计算被接受后用 `librpa-database-intake` 归档回数据库，不要只留在材料计算目录。
材料 Coulomb/Cs/shrink/密度/速度矩阵只能作为该计算的证据，不能跨材料复用。
已经选定并验证过的元素不因新材料而重做 PP 家族/PBE-head 筛选；
普通材料 PBE/EXX 检查与重新筛选元素是两件事。尊重用户停用二维 aims head 的决定。

按 **同赝势 PW/NAO 的 PBE 基组检查 → FHI-aims 全电子 PBE 对比 → head 筛选 → 入选体系 GW** 的顺序执行。这个流程筛选的是具体材料中的 PP+NAO 表示，不是为整个赝势库做永久排名。用户已授权的计算按各阶段结果推进，不重复索要同一范围的授权。

## 冻结定义

- 使用同一结构、XC、磁态、相对论/SOC口径、电子温度和 k 点定义。第一轮不要让三个赝势各自优化结构，否则几何误差与电子表示误差无法分离。
- 优先使用论文或 SI 的原始结构和 band k 路径。登记来源、坐标哈希、晶格/倒格坐标约定、端点、每段点数及重复端点处理；三个 PP 和 aims 使用同一份展开后的路径。文献没有提供坐标/采样数时明确标记，按参数重建不等于作者原始结构，内部统一点数不等于复现文献点数。SCF/head 的 BZ 网格与绘图路径分开登记。
- 对 GTH、SG15、Dojo stringent 分别记录版本、文件 SHA256、价电子及半芯态、NLCC、相对论处理。不能用另一个赝势产生的 NAO、ABFS、密度、vxc 或 PyATB 文件。
- **先查存量，再生成缺项。** 先搜索共用库、已验收 producer 的 STRU/输入 manifest、旧基组生成目录和已有轨道库，收集匹配 PP、物理 NAO、for_aux、ABFS、来源与哈希。有现成组合就先复用，不能因为新建了项目、改了文件名、想统一训练 Ecut/半径而重生成。仅当确实缺少匹配资产，或受控 PBE/head/RI/EXX 检查定位到某项表示不够时，才登记缺项/失败证据并生成；EXX 失败本身不自动授权重生成物理 NAO。不默认每种 PP 都新生成一套。
- 各 PP 使用自己的匹配 TZDP；登记文件头中实际各 l 通道数、半径、训练结构、训练能窗、spillage 和生成程序哈希。同叫 TZDP 不表示同维数或同精度；文件名可能漏写 g 或更高 l，不能按文件名计数或删掉通道。已有非 TZDP 但验证过的组合可作为历史对照，不改名冒充 TZDP。
- 用完整 PP 哈希判断是否是同一版本，而不是只看 GTH/SG15/Dojo 名字。仓库中部分 Dojo-NC-SR 元素可能与 stringent 字节相同，另一些并不同；逐元素核对，不能整体替换。历史 producer 使用过某 ABFS，不自动证明其原始生成 PP/NAO 的全部来源链；分别标记已验证用途和尚缺的生成证据。
- 在批准的服务器上运行物理计算/基组生成。本地只整理、解析和作图。使用项目 ledger、目录 formal ID、队列和哈希防重复；存在等价已验收结果就复用，存在活动作业就等待。
- 生产程序使用该项目已验证的版本契约，不能把一个历史 benchmark 的版本硬套给所有新项目，也不能仅为追最新 HEAD 重跑。读 `abacus-librpa-version-guard` 并记录实际采用的有界例外。

## SIAB 生成与复用

生成、调整或解释物理 NAO 前，读 [siab-generation-validation.md](references/siab-generation-validation.md)。不能只检查 `SIAB_INPUT` 中的 TZDP 标签。

- 已有匹配且验证过的 PP+NAO 优先复用；换 PP 价电子空间不属于轨道单变量实验。半芯态增加时按实际壳层设计候选，不机械翻倍所有径向层级，也不把另一价电子空间的小基组直接移植过来。
- 留存 `SIAB_INPUT`、每层实际 optimizer `INPUT`、参考 PW 输入/占据、随机种子、系数和 spillage 全历史。核实 `auto` 的实际权重和 `fix` 的冻结范围；增加 PW `nbands` 不等于给空态增加优化权重。
- 区分电子展宽与径向端点平滑，区分训练 Ecut 与材料 SCF Ecut。库中的 100 Ry/10 bohr 是已验证组合的参数，不是所有赝势的生成默认值。
- 分别检查原子径向 Gram、晶体 `S(k)`、局部 RI 求逆矩阵和最终 full Coulomb；任何一个的正定性都不能替代其余检查。PBE 良好、spillage 小不保证 EXX 稳定。
- PP+NAO+ABFS 同时替换且 EXX 改善，只能确认替代组合的有效范围。需固定 PP 的轨道对照，才能将原因归到轨道生成；不能因成功就宣称旧求逆代码有 bug。

## 第一关：先 PBE，不先生成三套 GW 链

1. 每个 PP 比较收敛 PW 与自己的 TZDP PBE，隔离 NAO 不完备性。对带边附近和 head 所需空态能窗分别检查，增加半径/径向层级或训练空态能窗的控制必须单变量。
2. FHI-aims AE 使用相同结构和 XC/相对论设置；从 intermediate 或项目已有更高等级开始，并通过加密积分网格和更大基组证明所关心的差异不是 AE 数值误差。intermediate 不是自动精确。
3. 先确认 SCF、电荷、占据、正带隙和 overlap 条件；再比较基本/直接带隙、谷间差、带边层/轨道成分，以及选定能区的色散。不要把 0.15 eV 等经验数写成所有材料的有隙硬门槛。
4. 半芯态数不同，不能跨 PP 对齐相同的绝对 band index。先按占据和价带顶附近物理态建立对应；PBE/GW 作图保留原始索引，禁止跨占据边界排序。
5. 每幅色散图可各自 VBM 对齐；带阶、电子亲和能、功函数必须用一致的电势/真空参考，不能用独立 VBM 对齐后的图作带阶判断。极性层报告两侧真空势。
6. 判据在看排名前登记，结合目标物理量设置误差预算。例如要判断 20 meV 的谷差，不能把 50 meV 的 PBE 表示误差称为通过。数值误差范围内相同的候选保留为并列。

## 第二关：与 aims 比较 head

运行前必须读 [response-contract.md](references/response-contract.md)。它区分原稿的 head 代理量、含局域场的宏观介电函数，以及二维面极化率。

- 在共同虚频区间、共同坐标轴和同一响应定义下比较完整可用张量，至少分别报告面内 xx、yy。非对角量不能用接近零的分量做相对误差分母。
- 对 PP 的速度矩阵必须包括非局域赝势贡献；NAO 非正交/位置矩阵项也须按实现包含。不能把裸动量直接当成所有 PP 的速度。核查 AE 的相对论、芯态参与及空态截断口径。
- head 由 PBE 态和跃迁矩阵得到，不需要先跑 GW。使用同一 SCF producer 的完整 k 网格生成 PyATB，不用能带路径代替 BZ 积分，不跨 PP 复用速度矩阵。
- aims 参考只计算到完整 head，不计算全电子自能或 QP。先核实当前二进制的输出路径和停止条件；不能虚构 `head_only` 关键字。若现有接口必须进入导出流程，完整张量全局归约、写出关闭、频率/维数/有限值检查后可按用户授权停止本作业，单独标记“head 导出完成后受控停止”，不是 aims 全流程成功。部分文件、只有各向同性迹或开始输出一行均不足以停止并验收；不得把无 HDF5 支持的程序用于 HDF5 动量输出。
- 收敛 k 网格、空态能量上限、NAO/AE基组和积分参数，避免把不等同的 NBANDS 数当成相同能窗。
- 原稿 $D_\varepsilon$、$D_\varepsilon^{low}$ 保留为明确标注的复现指标；二维主排名用真空无关的面内响应，不直接比较被真空稀释的超胞 $\varepsilon$。
- 5%/10% 是原稿两个 GaAs PP 的经验范围，**不是通用二维阈值或 GW 精度保证**。不能因 stringent 名称、更大价电子数或更接近期望 GW gap 预先选赢家。

## 第三关：选择与 GW

- 先通过 PBE，再按 AE 响应差与数值不确定性排序。若 xx/yy 或低频/整体指标冲突，保留候选，不强行用任意加权总分给唯一排名。
- 入选 PP 优先复用与物理 NAO 匹配的已有扩展 ABFS；缺失或检查失败才按 `abacus-librpa-abfs-orbital` 生成：`for_aux` 轨道仅用于辅助基生成，保留物理 TZDP 不变。物理轨道止于 d 时加平滑 f/g，已有 f 时按 recipe 加 g；已有 g 的半芯体系须检查缺失角动量和生成器能力，不能盲目套用同一 f/g 配方。检查维数、conditioning、全 q 库伦有限/厄米/PSD及谱尺度。EXX 和近带边检查通过后，才计算同源 GW；head 相似不能检出所有芯-价交换、局域场或短程自能误差。
- 正式 GW 启用 shrink 和对称性。当前已验证 LibRPA 输入使用 `use_shrink_abfs=t`、`use_symmetry_exx=t`、`use_symmetry_gw=t`、`use_symmetry_rpa=t`；每次仍核对该二进制的实际参数。必须存在同 producer 的 reader-v1 shrink 数据/变换、basis_out_shrink、IBZ/star/symmetry 文件，并通过当前程序系列的 matched symmetry/full-q 检查。元素库不提供跨材料通用 shrink 变换。
- 严格二维使用该项目已验证的完整 Coulomb 与 analytic complete-Wc Gamma 路线；不把 cut compatibility 文件误作 full，不把 3D averaged head 直接塞进 2D 修正。
- 常规短 NSCF/PyATB（预计 30 分钟内完成）按用户约定在远程登录节点限资源运行；预计超过 30 分钟的任何计算（SCF、NAO 生成、GW 等）必须经 Slurm 提交到计算队列，不得在登录节点运行；估计不确定时一律走 Slurm。
- GW 检查虚轴自能、原始 PBE-indexed frontier、谷序、低能连续性、Padé根及高态 NaN/侵入。分别标记低能有效和全谱有效；不得挑一个接近实验的 gap 忽略失败。

## 交付

保存 PP/NAO/结构/版本 manifest，PBE误差表，AE及PP的原始 head 张量与转换定义，共同频率网格、各方向误差和不确定性，最终选择理由，以及每个 job 的状态。结果写入 paper 前重建并检查实际图页。未有计算输出时标为待算，不能把计划阈值写成实测误差。

将 PP、物理 NAO、生成输入和哈希归档进 LibRPA 数据库：用 `librpa-database-intake` 建一条新记录，而不是另建本地目录。数据按 family/element/PP-hash/NAO-hash 不可变保存，生成证据与选择记录分开。选择记录必须引用具体材料、结构、PBE/head 报告及有效能窗，不能把“生成完成”标为“筛选通过”。额外 ABFS/for_aux 单独登记并关联物理 NAO，不混入 NUMERICAL_ORBITAL。未进数据库的资产，下一个算例看不见。

随附 `scripts/compare_response.py` 只处理已核实同一定义的 CSV，不负责推断原始 aims/PyATB 文件单位、修复数据或自动提交 GW。

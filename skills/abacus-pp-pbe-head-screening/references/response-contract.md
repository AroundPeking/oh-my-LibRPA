# 响应定义与定量比较

## 原稿依据

用户指定的参考源为
`/Users/ghj/同步空间/overleaf/GW_pseudopotential_NAO 2/output/overleaf/BS15393_Overleaf_source_20260905/main.tex`，Sec. Effects of the choice of explicitly treated valence electrons on dielectric screening，标签 `eq:macroscopic_dielectric`、`eq:dielectric_metric`、`eq:dielectric_low_metric`。

该稿用 `qhat^T H(iw) qhat` 的 **head** 作为屏蔽比较量；实施时不能把名称中的 macroscopic 自动理解为包含局域场的 `1/[epsilon^{-1}]00`。后者一般不等于 epsilon00。比较两代码必须选择同一个量，同样的张量或同样的方向平均。不得修改参考稿以掩盖这一区别。

原稿指标：

\[
D_\varepsilon=\sqrt{\frac{\int|\varepsilon^{PP}-\varepsilon^{AE}|^2 d\omega}
 {\int|\varepsilon^{AE}-1|^2d\omega}},\quad
D_\varepsilon^{low}=\max_{\omega\le0.1\mathrm{Ha}}
 \frac{|\varepsilon^{PP}-\varepsilon^{AE}|}{|\varepsilon^{AE}|}.
\]

论文在共同区间 0.00339775--20.35418064 Ha 上按 log(omega) 线性插值，积分测度仍是 **d omega**，不是 d log(omega)。指标约 2.1%/5.3% 与 13.2%/28.0% 对应两个 GaAs 价电子选择，不能作为跨材料已验证定律。无共同低频数据则 low 指标不可用，不能报告 0。

## 二维必须移除真空稀释

以 Gaussian/原子单位为例，对于对应的面内、无局域场 independent-particle head，在已收敛的孤立层极限：

\[
H_{ab}^{3D}(i\omega)=\delta_{ab}+\frac{4\pi}{L_z}
\alpha_{ab}^{2D,0}(i\omega),\quad a,b\in\{x,y\}.
\]

这里 `Lz=volume/in-plane area` 是垂直几何高度，不是斜晶胞第三矢量的长度；`alpha` 的长度单位随 Lz，SI 制不能照搬 4pi。若程序直接输出二维系数，从源码中的面积、spin和k权重确定映射后使用，不再乘一次 Lz。

等价的小 q 关系（符号采用 chi0 为负的通常约定）：

\[
\chi_{2D,00}^{0}(\mathbf q,i\omega)
=-q_a\alpha_{ab}^{2D,0}(i\omega)q_b+o(q^2),
\quad
\varepsilon_{00}^{2D}=1+2\pi q\,\hat q_a\alpha_{ab}^{2D,0}\hat q_b+o(q).
\]

因此严格二维 q=0 的 epsilon00 都趋于1，不能拿这个1筛选赝势；要比较其小q斜率/alpha。以上是响应**表示与比较定义**，不是修改本项目 Gamma-cell算法的授权。面外响应、local-field-included epsilon、极性层和各向异性需另核查映射，不能套面内公式。

用于二维主排名的指标：

\[
D_\alpha=\sqrt{\frac{\int\|\alpha^{PP}-\alpha^{AE}\|_F^2d\omega}
 {\int\|\alpha^{AE}\|_F^2d\omega}},\qquad
D_\alpha^{low}=\max_{\omega\le0.1\mathrm{Ha}}
 \frac{\|\alpha^{PP}-\alpha^{AE}\|_F}{\|\alpha^{AE}\|_F}.
\]

同时单列 xx、yy 的偏差，不掩盖方向性。近零分母报告不可定义，并使用带单位的绝对误差，不能靠加任意 epsilon 制造有限排名。二维 alpha-low 与原稿 epsilon-low 不同，要分别命名。

## 不能省略的实现核对

- 无 SOC 的非局域 PP：`v=(i/hbar)[H,r]` 包括 `[V_NL,r]`。核查实现实际导出的 velocity/dipole定义、能量单位及归一化，而非仅凭文件名。
- AE 是否 frozen-core response、包含哪些芯态跃迁、scalar relativity是否匹配，分别记录。用相同绝对 NBANDS 对比不同价电子数通常不公平，应控制空态能量范围并收敛。
- k权重和spin因子不得重复乘；BZ积分使用完整网格或已验证的对称性恢复。频率数、频率节点、面积和Lz均需显式记录。
- 含非局域势/非正交基时，通过更严格空态收敛、选点有限q或已验证的速度实现核查 response；不能通过调节 normalization 让曲线人工贴合。

## CSV比较工具契约

CSV 列为 `omega_ha,xx,xy,yx,yy`，张量分量为实虚频响应。脚本要求 `--quantity alpha2d` 或 `--quantity head3d`。head3d必须分别提供两代码的垂直高度（bohr），且仅限已核查上述转换的面内 head。工具拒绝 NaN、不递增/非正频率、无重叠或无低频覆盖；不外推，不作全电子精度保证。

不同候选务必使用**同一个共同频率区间**；需要多候选排名时用 `--omega-min`、`--omega-max` 显式锁定，不让每对数据自行选不同范围。

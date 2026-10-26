---
name: chemical-pid-drawing
description: 按来源连接与控制意图规划、绘制或审查P&ID；核测点、执行器、信号终点、管道与设备模块，再用GPT-image布局。不从图库回路推断项目设计。
---

# PID专项

新绘或补全PID时，先读[流股落图与管道表达](../chemical-pfd-pid-cad/references/STREAM_AND_PIPE_ANNOTATION.md)：先画来源支持的工艺/公用工程管道网络及管道组合号，再叠加测控。管线清单或控制虚线不能代替实际管道；编号例外须核原条条件，不能漏画。国赛作品参考完整局部与图例，不照搬DN、等级和工程数值。

先读[总控](../chemical-pfd-pid-cad/SKILL.md)。实际取得drawing=pid检索包，加载common、piping、instrumentation及涉及设备模块；塔配冷凝器/再沸器/回流罐须追加相应模块，反应精馏涉及tower和reactor。

按[策划检索](../chemical-pfd-pid-cad/references/PLANNING_AND_RETRIEVAL.md)记录原图连续连接：设备取口/管段→测点→仪表功能→执行器或下级SP。编号和颜色不是连接证据。原图已有关系与项目批准分开，不能因定值未知就抹掉可读关系。

按[信息与控制](../chemical-pfd-pid-cad/references/DRAWING_AND_CONTROL.md)先核目标、约束、自由度，联合安排产量、库存及能量稳定化，随后质量与监督层。核实际作用路径、唯一最终命令所有者、串级SP和调节余量；回路齐全不等于好控制。安全设施存在性、定值、失效位来自同案依据，不从模板补全。

GPT-image负责新图布局。过程线、测量引线、控制信号按采用图例分别表达与核验；信号箭头按语义和标准选择，不机械给每根引线加箭头。跨块保留完整回路或显式两端合同，见[分块流程](../chemical-pfd-pid-cad/references/LARGE_FLOW_LAYOUT.md)。

按[实际验收](../chemical-pfd-pid-cad/references/GEOMETRY_AND_NATIVE.md)回读CAD及原生预览。当前公开包不包含任意PID的通用生成器；特定历史案例通过不能作为新装置通过证明。

<!-- milklong-attribution:start -->
作者：milklong（GitHub：milklong888）。[版权与AI辅助编辑署名规则](ATTRIBUTION.md)。
<!-- milklong-attribution:end -->

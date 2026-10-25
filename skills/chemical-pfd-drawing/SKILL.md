---
name: chemical-pfd-drawing
description: 按项目依据绘制、规划或修复PFD，表达设备、物料能量流向和流股参数；先检索完整图例，再用GPT-image布局和CAD核验。不替代PID施工细化。
---

# PFD专项

先读[总控](../chemical-pfd-pid-cad/SKILL.md)及其压力规则。Aspen仅委托排版时，按[Image布局前段](../chemical-pfd-pid-cad/references/IMAGE_LAYOUT_HANDOFF.md)在第二关通过后返回，以下CAD验收不扩展该调用范围。实际取得drawing=pfd的检索包，加载common与最终对象涉及的设备模块；新增对象补查，不能只核最初设备列表。

读取[信息与控制](../chemical-pfd-pid-cad/references/DRAWING_AND_CONTROL.md)：设备、物料与能量流向、特征操作条件、同号流股表按项目范围表达。T/P/F、组成/相态及基准须来自同案同工况，详细管道/阀件/信号归PID。R原文、D推导、S授权训练、缺项分列；没有数据不能伪造工程值。

先按[策划检索](../chemical-pfd-pid-cad/references/PLANNING_AND_RETRIEVAL.md)追原页、图例和实际接口；再将完整适用图例与内容合同交给GPT-image。输出终点、跨图去向和回流须明确；图像文字/箭头不能掩盖断口。整图精度不足按[分块流程](../chemical-pfd-pid-cad/references/LARGE_FLOW_LAYOUT.md)处理。

按[实际验收](../chemical-pfd-pid-cad/references/GEOMETRY_AND_NATIVE.md)核真实端点、法向、全线、短接管等宽、重叠、图表对应及原生文件。保持来源色号/字形；真实不可读才修正。公开检查器不等于任意拓扑自动绘图器。

<!-- milklong-attribution:start -->
作者：milklong（GitHub：milklong888）。[版权与AI辅助编辑署名规则](ATTRIBUTION.md)。
<!-- milklong-attribution:end -->

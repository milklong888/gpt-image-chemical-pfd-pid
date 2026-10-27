# Image 分阶段交接

本脚本无新增第三方依赖，但会调用既有知识工具；须按知识工具 README 配好原有运行环境。复用同一 `tools` 下的本地 `drawing-knowledge/retrieval_gate.py` 或公开版 `drawing-knowledge/engine/retrieval_gate.py`；缺少同包入口时明确失败，不暗中加载另一套用户私库。不启动 Image、CAD、Aspen，不重建索引，也不新建 RAG。

## 两个明确阶段

`spec.stage` 必填，只能是 `exploration/standard_revision`；缺省拒绝，不默默落到旧严格模式。`drawing_use` 仍必填 `engineering_pfd/engineering_pid/aspen_native_layout`，不因图例未知改成 BFD。

| 阶段 | 本次可生成内容 | 请求状态 |
|---|---|---|
| `exploration` | 首次探索图；固定已知拓扑、准确标签和已有数据，未知图例/画法逐对象登记 | `candidate_unstandardized` |
| `standard_revision` | 对首图实际问题、标准替换方案和同版输入完成三轮独立审核后，允许二次生成 | `reviewed_revision_request` |

两阶段请求均为 `cad_allowed=false/delivery_allowed=false`。探索通过不能继承为标准阶段通过；三轮只准二次生成，不声称首图已改好或尚未生成的二次图已符合国标。二次图须实际看过、按适用标准和完整图例修改复核；有硬错继续改/再生成，之后才可按下游门返回已核布局或进入 CAD。原生 CAD 接口/端口/回读另审。

Image 两阶段都不要求字体参考，不以 Image 验收字体、字形或准确造字；只要求标注空间和可辨对象 ID。准确标签及数值仍保留在语义合同中，实际字体可用性、字形、准确落字与缺字/乱码由 CAD/Aspen 落字后的原生输出及回读负责。可选 `font_reference` 仅作普通视觉参考，核验其图片身份/hash，不变成 Image 字体门槛。

大流程沿用原 [分块生成与总排布工作流](../../references/LARGE_FLOW_LAYOUT.md) 和 [Image 输入合同](../../references/IMAGE_INPUT_CONTRACT.md)，不新造分块算法或全局 schema；本入口不自动分块、拼接或完成总图装配。先理解工艺和模块耦合、划定功能块；每块按“探索→标准修正三轮→二次生成→实际图后核改”完成，合格小块再按原工作流给 Image 做整体排布。总图侧重模块位置和跨块连接，不塞每块全部内部细节。目标图层与对象/连接范围由当前合同给；密度超过可读精度就回到分块，不整体密排。完整 CAD 任务保留先小图 CAD、再宏观组装路线，Aspen 只布局仍沿用原例外。

## 探索阶段

仍须真实检索、取得当前 packet 并通过原 `check_receipt`。图例未知不授权新增设备、流程、连接、数值或虚构来源。已知完整符号仍照用，不按矩形外观禁用真正矩形设备；未知项允许 Image 探索合理表达，不能默认用无意义功能方框，不能称作已核原图例。

`gaps` 必须存在，每项为 `{id, object_id, missing, retrieval_observation, exploration_boundary}`；`missing` 是 `symbol/drawing_rule` 的非空子集，记录本次实际检索未定项与探索范围。未知设备图例的合同表达为 `{kind: exploratory_symbol, gap_id: 本对象缺口ID}`。逻辑 split/mix/junction 仍为连接逻辑，包界仍须明确授权。所有对象由已采用规则的 `scope_ids` 或本对象的 `drawing_rule` 缺口覆盖。

全部符号未知可 `symbols=[]` 且无 `symbol_atlas`，没有任何适用参考时可 `references=[]`。也可提供普通视觉参考；所有提供的图片仍核验身份/hash，`font_reference` 不强制附 source。`applicable_reference` 仍须有来源；来源可用真实 packet 正文或合同登记的当前项目存档，经 Gate1 实读，不用把私有指令写入公共库。没有已知适用画法时可 `applicability=[]`，但每个对象须登记 `drawing_rule` 缺口。已知符号不能借探索省略其完整 atlas/source。

探索 Gate1 除原有合同、全部已知符号/规则/授权/位置项外，还须逐缺口有 `category: exploration_gap/target: 缺口ID` 记录，至少引用 `contract/receipt`，检查检索缺口和探索边界。有实际参考图片时还须 `reference_images` 记录；references 为空时不制造图片或假证据。不得继承标准修订三轮结论。

## 标准修订与三轮审核

`standard_revision` 必须 `gaps=[]`，恢复逐对象真实完整符号、条/表/图/页、实际 atlas 和全部对象适用表达覆盖，实际首图仍必须传入，字体参考不是门槛。原 PDF 有图例而检索 gap 时，先溯源补库并取得 fresh receipt，不能随填 hash 冒充规范图例链路。

新增 `revision: {first_image: {path, sha256}, correction_input: {path, sha256}}`。`first_image` 是首图实际文件，还须以 `role: first_image` 的同一文件放入 `references`，实际传给 Image。`correction_input` 是受审修正说明/对象映射/更正输入的 UTF-8 文件，其**全文纳入实际 prompt**，作为已审核更正要求，服从当前语义合同和已采用标准/完整图例，不是只绑定 hash。

三轮复用 Gate1 的 `standard_review_rounds`，不用另建台账，按顺序为：

1. `basis_and_symbols`：依据、图例和包界；records 覆盖全部 `symbol_selection/industry_applicability/package_authorization`。
2. `connections_and_annotation_application`：连接、准确标注与规则应用；覆盖 `semantic_contract/industry_applicability/spatial_constraint`。
3. `revised_input_and_omissions`：首图实际问题和同版修正输入的整图、漏项审核；覆盖全部 Gate1 项。

每轮有不同 `reviewer`、同一 `scope/material_sha256`、同一 `first_image_sha256/correction_input_sha256`、引用 `contract/revision:first_image/revision:correction_input` 的 `evidence_refs`、非空 `application_note`，以及既有格式的有依据 `records`。应用说明确认更正如何落实到**受审输入**，不能把计划称成首图已改好。任一输入版本变化都按新摘要重审；实际人员/代理独立性和实读由工作流负责。

## 来源、表达与布局

普通引用 `{path, sha256}`。工程图例/规范来源增加 `locator: {kind, value, physical_pages}` 和 `receipt_evidence_ids`，kind 为 `clause/table/page/figure`。原生 CAD 可用 `native_handles`。页/句柄须属真实 packet 返回/固定上下文的对应正文节点，匹配 `source_path/source_sha256`。正文及页/句柄支持 `ClauseCandidate/CasePattern/Requirement/SymbolRepresentation`；Source 只允许有物理页的 `page:` 锚点，来源登记和版本元数据不能代替正文。具体图号/条文语义由 Gate1 对绑定原页核读。

合同可选 `source_records: [{id, record_kind, file, scope_ids}]`，record_kind 为 `user_instruction/project_approval`。包界授权、用户位置要求和参考来源可用 `locator: {kind: project_record, value: 记录ID}` 引用当前已读来源文件，不填 receipt IDs。规范依据仍走 packet；工程符号/行业规则不能伪装项目记录绕过。

仅 Aspen 模式可用 `current_case_native_reference` 记录，另含 `source_id/case_ref`，file 为同案原图标截图，case_ref 绑定当前 BKP/冻结上游 case 的 hash。符号/表达以 `locator.kind=native_case` 引用；atlas 须同一实际截图，Gate1 相应项还引 `project_record:记录ID/native_case:记录ID`。不写公共库、不声称国标，原生截图不能充当包界授权。

设备用 `equipment_symbol`（Aspen 用 `aspen_native_icon`），逻辑节点只用 `logical_node`，包界 `functional_block` 须完整符号及逐对象授权，native_block 仅 Aspen；探索只增加上文明确的 exploratory_symbol 分支。位置默认自由；其它位置锁定须有用户/适用条文依据和独立审核，不用方向词正则。避碰、留白、可读连线、接口方向仍保留。主图可留数据区容量，不强塞每行全部精确数值。

**两阶段共同严禁蛇形塞图**：不得为把全流程塞满单框而逐排往返、多层长线横贯、设备/标注密排（serpentine/boustrophedon packing）。空间不足应增大画布或清晰分块，不能缩字或压缩间距；主流向清晰、设备周围留白。这是当前用户明确硬约束，无需逐案例另行审批或 RAG；有据位置约束也不能放行这种塞图。该限制不删除工艺真实回流，合同中的真实有向回路必须保留。

## 文件交接与验证范围

```powershell
python prepare_image_request.py spec.json --review-material --output review-material.json
python prepare_image_request.py spec.json --output prepared-image-request.json --diagnostic failure.json
```

待审材料 `non_request=true`，含精确 prompt 和绑定，不含 imagegen_arguments；Gate1 未生成时可先出材料，其余阶段输入须齐。三轮在 Gate1 内绑定当前材料摘要，最终 Gate1 hash 单独绑定以免循环。调用前用 `verify_prepared_request` 重查后原样传入返回参数。无参考图的探索请求**省略** `referenced_image_paths` 字段，不传空数组充当编辑，不伪造参考图；有实际参考时按已核图片顺序传入。失败不写请求，可写新诊断，已有输出不覆盖。prompt 保留语义、图册定位、规则、缺口/更正要求，审计路径/hash 留 bindings。

`example.synthetic.json` 仅为有占位 hash 的字段示例，不是工程证据或可执行 packet。

**本轮字体/标注澄清仅作文本审阅，依用户要求没有运行测试、验证脚本或启动任何绘图/模拟应用。此前48项测试只验证旧候选，与旧入口另行归档，不作为新阶段当前可运行测试入口；不能算新阶段及本次澄清已测，也不能用旧结果宣称当前版本通过。** 原测试使用合成 packet/1×1 PNG/来源，执行真实 check_receipt，仅隔离大型索引健康检查，不等于真实 RAG 查询。

本入口不拦直接工具调用，不证明人工实读、人员独立、来源语义真实、工程对象完整或标准合规。探索通过不继承到标准阶段，三轮通过不证明未来二次图像符合；图后修改复核和 CAD 回读不能省略。

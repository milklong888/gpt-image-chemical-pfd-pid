# Image 交接 v2：首图与 CAD 后布局优化

本脚本无新增第三方依赖，但调用既有知识工具，须按知识工具 README 配好运行环境。复用同包 `drawing-knowledge/retrieval_gate.py` 或公开结构 `drawing-knowledge/engine/retrieval_gate.py`；缺少入口明确失败，不借另一用户私库。不启动 Image/CAD/Aspen，不自动分块、合并或重画，也不新建检索框架。

## 模式和阶段

`schema` 必须 `image-handoff/v2`，`workflow_mode` 必填 `full_cad/image_layout_only`，`stage` 必填 `exploration/cad_layout_refinement`。旧 `standard_revision` 明确拒绝，不能沿用旧“首图三轮后立即二次生成”的顺序。`drawing_use` 仍为 `engineering_pfd/engineering_pid/aspen_native_layout`。

| 模式/阶段 | 作用 | 输出状态 |
|---|---|---|
| 任一模式 `exploration` | 正常化工流程首图；逐对象记录未知图例/画法 | `candidate_unstandardized` |
| 仅 full_cad 的 `cad_layout_refinement` | 实际首版 CAD 审核三轮后，将 CAD 预览交 Image，只优化布局 | `reviewed_cad_layout_refinement_request` |

请求均 `cad_allowed=false/delivery_allowed=false`，不自动授权 CAD 操作或通过验收。`image_layout_only`（包括 Aspen 只布局）在前段核改后返回，不为满足后阶段而新建 CAD；没有实际 CAD 不能声称完成 CAD 后二次优化。

## 当前完整顺序

1. 检索要素标准，选用适用的国赛整图/局部/完整图例并实际传图。遵循[国赛图例与塔画法](../../references/COMPETITION_LEGENDS_AND_TOWERS.md)逐图种判断适用/回退，不把无关参考冒充国赛，不强迫每种图都有国赛出处。
2. 按需确认车间边界；已有明确单元范围不强造车间，多车间按车间逐一推进。正常完整流程首图优先，清楚就不切；策划已能确定或实际反馈显示密度/精度不足，才车间内功能切块，沿用[大流程规则](../../references/LARGE_FLOW_LAYOUT.md)与[输入合同](../../references/IMAGE_INPUT_CONTRACT.md)。未知图例可探索，但不得默认无意义方框、增造流程/数据或伪称原图例。
3. 按标准修正首图，再转首版 CAD，准确信息和字体在原生 CAD 落图。探索假设未修正前不能直接作正式 CAD 源图例。
4. 如车间内实际切块，先真实 CAD 合并并核跨块每股连接、接口；没切块则记录真实整图范围及逐股检查，不能伪造合并。
5. 对这份实际 CAD 作三轮标准、国赛风格/图例和完整性审核，绑定同版 CAD/预览/检查记录/布局输入。
6. 把审核过的 CAD 预览交 Image 二次优化排线布局；只采纳位置、走线、留白，不采纳图例、字、数据或拓扑变化。
7. 据冻结合同和原图元 CAD 重画，并完成终验。Image 结果不是新工程依据，也不代替原生字体/连接/数据验收。

不增加自动全局拼接 schema。两阶段共同严禁蛇形塞图：不能逐排往返、多层长线横贯、设备/标注密排来塞单框。空间不足扩大画布或回到必要分块，不缩字挤间距；保留真实工艺回流。

## 首图与来源规则

探索仍须真实检索 receipt，经既有 `check_receipt`。`gaps` 项为 `{id, object_id, missing, retrieval_observation, exploration_boundary}`，missing 为 symbol/drawing_rule 非空子集。未知设备图例用 `{kind: exploratory_symbol, gap_id}` 绑定本对象缺口；已知完整图例仍必须附 symbol_atlas。所有对象由已有适用规则或自身 drawing_rule 缺口覆盖。逻辑 split/mix/junction 只用 logical_node，不能伪装设备；包界 functional_block 仍须明确授权。

全部设备图例未知可 symbols=[]；仍须查找并实际附上可用的国赛整图/局部风格参考。只有确实没有适用参考且记录检索缺口时才可 references=[]，无图时请求省略 referenced_image_paths，不传空数组或假图。字体参考可选，Image 只需标注空间与可辨 ID；准确字体、字形、文字和数值由 CAD/Aspen 原生落字和回读验收。提供的可选图片仍核身份/hash，不据此验 Image 字体。applicable_reference 须有来源，可为适用国赛整图/局部等，国赛身份和回退由独立审核实读，不靠命名猜测。

工程图例和规范来源保留 `{path,sha256,locator,receipt_evidence_ids}`；locator 为 clause/table/page/figure 并绑定 packet 正文原页或 native_handles。仅来源登记/版本元数据不算正文。ClauseCandidate/CasePattern/Requirement/SymbolRepresentation 要有正文及页/句柄；Source 仅允许 page: 原页锚点。路径/hash/范围机械核验，具体条/图语义由 Gate1 核读。

当前用户/项目批准仍可在合同 source_records 登记指令存档/hash，授权/位置可 project_record 引用，不强迫私有指令入公共库；工程符号/规范不能伪装项目记录绕过。Aspen 原图标可用 current_case_native_reference，绑定可读图册、case_ref、source_id 和对象范围，经 Gate1 对实际同案源核读；不声称国标。

## CAD 后二次请求

`cad_layout_refinement` 仅 full_cad，gaps 必须空，逐对象完整真实符号、原页条款/图例、适用范围、逻辑节点等旧要求保持。revision 固定为：

```json
{
  "cad_file": {"path": "reviewed-first-cad.dwg", "sha256": "..."},
  "cad_preview": {"path": "same-cad-preview.png", "sha256": "..."},
  "assembly_evidence": {"path": "actual-scope-assembly-stream-checks.txt", "sha256": "..."},
  "correction_input": {"path": "layout-only-input.txt", "sha256": "..."}
}
```

CAD 文件必须存在、非空并以 dwg/dxf 为后缀；这不验证其真实文件格式或原生可读性。预览必须是实际图片，且同一文件以 references.role=cad_baseline 真正传给 Image，已知 atlas 也仍附图。assembly_evidence 是 UTF-8 实际范围、真实合并（或未切块说明）、逐股/接口检查及检查来源说明，不能用单个 true 自证。程序只检查文件存在/hash及非空文本，不解析 DWG 或自动证明合并/检查真实；独立审核必须实际读 CAD、预览与记录，发现空泛声明不批准。correction_input 的非空 UTF-8 全文实际送入 prompt，只能给布局改进要求，不能授权工程内容变化。

Gate1 schema 为 image-gate1-review/v2。保留原有 scope/material_sha256 与 records，增加 `category: cad_baseline,target: cad_baseline`，evidence_refs 至少含 contract 与 revision:cad_file/cad_preview/assembly_evidence/correction_input。standard_review_rounds 为三份独立 reviewer 的同版记录：

1. standards_and_symbols：标准与完整符号/授权，含 cad_baseline。
2. competition_style_and_legend_application：适用国赛风格/图例、标准优先、连接与标注应用，含 cad_baseline、参考图、符号/适用/位置/合同项。没有适用国赛例时实际记录回退，不能强行认定赛事来源。
3. cad_completeness_and_interfaces：CAD 整图完整性、遗漏及真实合并/逐股接口，覆盖全部 Gate1 项。

每轮绑定 scope/material_sha256 与 cad_file_sha256/cad_preview_sha256/assembly_evidence_sha256/correction_input_sha256，evidence_refs 含四文件和合同，有 application_note 说明实际 CAD 审核结论，records 使用原有带证据/观察/approved 格式。文件或 prompt/合同改变就重审，不继承首图通过。独立性/实读由工作流保证，程序不验证人员身份。

第二阶段 prompt 明确 LAYOUT ONLY，以审核过的 CAD 预览作基底。完整设备图例定义、标准、字体、字、数值和拓扑冻结；仅准已核位置变换及连接管线路径调整，不改变原符号内部几何；国赛案例仅风格，不能导入设备/控制/数据。只准位置/走线/留白的结果进入后续原图元重画与终验。

## 文件交接与未测边界

仍可用 --review-material 生成 non_request 材料供审核，再准备请求；实际调用前 verify_prepared_request 重查，并原样使用参数。材料和请求 schema 分别 image-review-material/v2 与 prepared-image-request/v2。既有输出不覆盖；失败不写请求，可写新诊断。图/来源/合同/receipt/工具自身/实际 CAD 证据/审阅与 prompt 都保留摘要绑定。

本次只作文本修订，按用户要求未运行测试、验证器、Image/CAD/Aspen。旧48项仅旧候选，不证明本 v2 可运行或新顺序已测。example.synthetic.json 是带占位 hash 的格式说明，不是实际工程证据。工具不拦直接绕过，不证明来源语义、实读、独立性、工程完整或合规；请求通过不等于最终 CAD 验收。

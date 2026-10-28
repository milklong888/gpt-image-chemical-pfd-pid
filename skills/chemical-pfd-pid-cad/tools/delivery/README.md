# 交付集合与文件身份对账

只使用 Python 标准库。作为完整CAD交付前的一致性检查入口；真实应用验证与离线校验分开记录。`import delivery_manifest`没有文件读写；仅调用函数或CLI才操作文件。它不启动CAD、导出器、PDF查看器，不发布成果。

目标是让“完整来源流股－明确授权排除＝本次图面显示集合”成为实际数据，三份制图/读图输出共用此集合；最后逐股逐字段核本版原生回读观测，防止旧显示集合的说明与新图混用。没有固定数量、用户名、字高、PC3、版式或项目单位。

## 1. prepare

```text
python delivery_manifest.py prepare --manifest prepare.json --run-id case-rev01 --out-root delivery-runs
```

`run_id`为1–80个ASCII字母、数字、下划线或短横线，首字符须字母或数字。`out-root/run_id`必须不存在，不覆盖旧run或输出。所有校验先于创建run；I/O失败或输入在写入期间变动时可能留下**没有prepare-record.json的未完成run**，应保留并另选run_id，不将残留文件认作已准备成功。

prepare.json只允许这些字段：

```json
{
  "schema": "delivery-prepare/v1",
  "source_data": {"path": "source-data.json", "sha256": "填实际64位小写SHA256"},
  "exclusions": [
    {"stream_id": "ZERO", "reason": "本次明确排除的具体理由", "authority": "项目采用记录或明确用户授权的准确定位"}
  ]
}
```

source-data.json为完整同案来源，不提前删去不显示流股。以下数值仅为合成格式例子：

```json
{
  "schema": "delivery-source/v1",
  "streams": [
    {"id": "S01", "fields": {"T": "320.000", "P": "220.00", "F": "1250.00"},
     "units": {"T": "K", "P": "kPa(a)", "F": "Nm³/h"},
     "source_ref": "同案文件身份、页/表/行及采用依据"},
    {"id": "ZERO", "fields": {"F": "0"}, "units": {"F": "Nm³/h"},
     "source_ref": "同案零净流量边界的准确来源；未定义温压不填零"}
  ]
}
```

每股字段集可不同；单位映射必须恰好覆盖其全部字段，均为非空字符串。无量纲采用明确单位字符串，例如`1`。值保留准确采用字符串，`320.00`与`320.000`视为不同；工具不换单位、不推断压力基准、不补缺值。未定义字段应在来源决定中说明，若不适用本次字段集则不创建该字段；不要填null、空串或NaN。所有源流股ID唯一，排除必须是源内唯一ID且有非空reason/authority；全部排空拒绝。authority是可追溯声明，程序不验证授权人身份或其工程合理性。

成功生成：

- `drawing-data.json`：含完整显示集合及每股原字段/单位/source_ref，可由CAD实施程序读取；同时保留完整来源文件身份、排除清单及理由。
- `streams.csv`：长表`run_id,stream_id,field,value,adopted_unit,source_ref`。UTF-8、标准CSV引用，按ID/字段排序；用文本读取器读取，Excel可能自行改数字精度。
- `reading-note.txt`：实际源/显示数量、全部显示ID、排除理由和授权，不另手写常量数量。
- `prepare-record.json`：同次run、源与prepare manifest身份、显示/排除集合及三份输出hash。

流股数据必须从这次`drawing-data.json`落图；工具不会替已有绘图程序换输入。

## 2. audit输入

```text
python delivery_manifest.py audit --manifest audit.json --output consistency-rev01.json
```

所有文件引用均为`{path,sha256}`，sha256严格64位小写十六进制。路径相对**所在引用文件**解析：顶层manifest引用相对manifest；export.outputs[].file相对exports记录。输出记录使用绝对路径。所有被引用文件必须存在且非空；既有audit输出不覆盖。退出0仅表示此次一致性前置记录成功，失败返回2且不写成功记录。

audit.json固定结构：

```json
{
  "schema": "delivery-audit/v1", "run_id": "case-rev01",
  "prepare_record": {"path": "delivery-runs/case-rev01/prepare-record.json", "sha256": "实际hash"},
  "files": {
    "drawing_dxf": {"path": "本次实施输出.dxf", "sha256": "实际hash"},
    "semantic_json": {"path": "本次语义合同.json", "sha256": "实际hash"},
    "native_dwg": {"path": "本次原生保存重开.dwg", "sha256": "实际hash"},
    "native_pdf": {"path": "本次原生打印.pdf", "sha256": "实际hash"},
    "native_readback_dxf": {"path": "该DWG回读.dxf", "sha256": "实际hash"}
  },
  "observations": {"path": "observations.json", "sha256": "实际hash"},
  "exports": {"path": "exports.json", "sha256": "实际hash"},
  "review_report": {"path": "review.json", "sha256": "实际hash"}
}
```

五个交付角色及完整source/prepare来源与三输出、观测、导出记录、审核报告、audit manifest必须为不同物理文件。工具对已存在文件使用`Path.samefile`，拒绝同一路径、符号链接或硬链接伪装成不同角色；独立存储但字节相同的文件不因hash相同而被误拒。既有输出文件若与输入为别名也拒绝；其他既有输出仍不覆盖。semantic_json必须是非空JSON对象，但此工具不解读其项目schema，也不把其余文件解释成真实DWG/PDF。audit会重新核源、排除集合并重新渲染prepare三输出逐字节比较，不仅信prepare-record里填过的hash。源/排除一变必须新run。

observations由原生回读方提供，固定结构：

```json
{
  "schema": "delivery-observations/v1", "run_id": "case-rev01",
  "native_dwg_sha256": "实际本版DWGhash",
  "native_readback_dxf_sha256": "实际本版回读DXFhash",
  "streams": [
    {"id": "S01", "id_handles": ["1A2"],
     "fields": {
       "T": {"text": "320.000", "adopted_unit": "K", "handles": ["1A3"]},
       "P": {"text": "220.00", "adopted_unit": "kPa(a)", "handles": ["1A4"]},
       "F": {"text": "1250.00", "adopted_unit": "Nm³/h", "handles": ["1A5"]}
     }}
  ]
}
```

每个应显示流股恰好一次，ID、全部字段和采用单位须与prepare同集合准确字符串一致；缺失、多余、重复、字段集变化或值差异均拒绝。ID与字段均须有非空十六进制文本句柄列表。允许多字段同MTEXT句柄，不虚构“每个字段一个实体”的要求。句柄本身不验证其确实属于DWG、是否可见、位置或字墨；这些仍由原生回读方与实际审阅负责。

exports.json要求三种原生输出各有退出码及audit.ok，并绑定相同文件：

```json
{
  "schema": "delivery-exports/v1", "run_id": "case-rev01",
  "outputs": {
    "native_dwg": {"file": {"path": "本次原生保存重开.dwg", "sha256": "实际hash"}, "exit_code": 0, "audit": {"ok": true}},
    "native_pdf": {"file": {"path": "本次原生打印.pdf", "sha256": "实际hash"}, "exit_code": 0, "audit": {"ok": true}},
    "native_readback_dxf": {"file": {"path": "该DWG回读.dxf", "sha256": "实际hash"}, "exit_code": 0, "audit": {"ok": true}}
  }
}
```

退出码必须是整数0，false不能冒充0；ok必须是JSON true，数字1不能冒充true。记录由导出/回读方据实际执行填写，不能手造成功掩盖失败；本工具不证明这些声明的真实性。

## 3. 同版审核报告

review.json固定结构：

```json
{
  "schema": "delivery-review/v1", "run_id": "case-rev01",
  "bindings": {"每个下列键": {"path": "准确绝对路径", "sha256": "实际hash"}},
  "scopes": [
    {"scope": "geometry", "status": "pass", "reviewer": "实际审阅者身份", "observation": "实际范围、发现及关闭情况"},
    {"scope": "typography", "status": "pass", "reviewer": "实际审阅者身份", "observation": "实际字体字形与打印复核"},
    {"scope": "native_visual", "status": "pass", "reviewer": "实际审阅者身份", "observation": "实际DWG与原生PDF查看范围及结论"},
    {"scope": "data", "status": "pass", "reviewer": "实际审阅者身份", "observation": "逐股数据与源集合对账"}
  ]
}
```

bindings必须**恰好**包括这些键：`prepare_record,prepare_manifest,source_data,drawing_data,streams_csv,reading_note,drawing_dxf,semantic_json,native_dwg,native_pdf,native_readback_dxf,observations,exports`，每个是对应本版文件绝对路径与hash。可由上游读取prepare-record及audit输入后整理，供实际审阅者审核；不要自动生成pass。scope恰好上述四项且各一次，所有reviewer/observation非空；不强迫四名不同人员，也不认证人员身份。

报告不引用自身，避免hash循环；audit成功记录另保存review文件身份及audit manifest身份。更换任一绑定文件、更新旧报告hash而不更新其中的交付身份、漏scope或非pass均拒绝。成功状态只用`consistency_passed`。

## 明确未覆盖

- 不保证来源流股JSON本身确为完整/正确同案来源；提供方与专业审核仍须核它。
- 不证明DWG观测提取、导出记录或审阅人的声明真实；不解析CAD几何/句柄内容，不验证PDF/字体、GB符合性或工程签发。
- 不绑定CAD生成算法或自动修改其输入，不管理图例选用、布局、单位采用/压力基准的工程决策。
- 文本精度/单位严格字面比较，不提供容差换算。CSV是辅助交换，JSON为权威字符串数据。
- 有限合成反例在`tests/test_delivery_manifest.py`；当前执行范围记录在项目验证状态，测试通过也不是图纸验收。

运行有限单元反例的命令：`python -m unittest discover -s tests -v`。文件读写故障可能留下未完成prepare目录或部分audit输出；成功前置记录必须以CLI退出0和完整JSON为准，不能凭文件存在判断。若文件在最后复验后再次被其他进程改变，本工具无法锁定外部软件；应紧接交付使用同版文件。

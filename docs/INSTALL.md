# 安装与运行

## 几何与可选原生工具

几何检查、路由适配、连续拱桥和指定箭头绘制顺序的入口是 [geometry](../skills/chemical-pfd-pid-cad/tools/geometry/README.md)。从仓库根目录安装并运行：

```sh
python -m pip install -e skills/chemical-pfd-pid-cad/tools/geometry
python -m unittest discover -s skills/chemical-pfd-pid-cad/tools/geometry/tests -v
```

没有独立安装 libavoid-js 时，真实路由测试明确跳过；其余几何测试仍可运行。安装和设置 runtime 的准确命令见上述工具文档。公开原生读取器目前仅编译验证；不会代为安装或启动 AutoCAD，也不把 DXF 检查写成 DWG 已回读。

基础离线测试使用 Python 3.11 或更新版本；Python 3.12为公开CI目标。安装 `requirements.txt` 后运行根目录测试。知识模型与文档解析为可选依赖，见知识工具附带说明；不会在基础测试中自动下载权重或调用收费图像服务。

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/install_skills.py --destination /your/agent/skills
```

安装器把五个Skill复制到指定目录。工具位于总技能目录内，其他专项通过相对链接引用；默认拒绝覆盖已有技能，避免覆盖本地完整版。使用新的目标目录先验证，再自行选择切换。

向代理提供项目依据和任务，例如：“使用 chemical-pid-drawing 规划这个塔的PID；先查塔、换热器、容器、管道、仪表模块和原件，保留已有回路，未知条件单列；核准内容后使用GPT-image布局，交付真实CAD和预览。”模型可用的工具与服务由使用环境配置，不在此仓库保存API密钥。

知识数据根独立于代码：原件、登记、解析、卡片、模块、corpus和索引属于使用者自己的数据。先用公开合成样例检查安装，再导入有权使用的资料。登记和建索引不代表条款/元件已可工程采用。来源更新后旧回执失效，重新检索并核对最终对象范围。

CAD检查工具仅在各自声明的输入/几何类型内工作。DXF通过不是DWG通过：需要原生DWG时，合法安装CAD，确认实际字体，保存关闭重开并回读，再看原生PDF整页和局部。商业程序与字体不随包提供。不要使用测试几何替代工程图例。

详细工具命令见 `skills/chemical-pfd-pid-cad/tools/` 内相应说明与 `--help`；公开包不提供退役旧引擎的一键全流程生成入口。

## 知识检索组件

源码和详细依赖位于 [drawing-knowledge](../skills/chemical-pfd-pid-cad/tools/drawing-knowledge/README.md)。基础测试与知识契约测试分开：

```sh
python -m pip install llama-index-core linkml linkml-runtime jsonschema PyYAML ezdxf
python -X utf8 skills/chemical-pfd-pid-cad/tools/drawing-knowledge/tests/test_portable.py
```

该测试真实运行装配、LinkML结构检查、来源/结果/模块门控与精确编号匹配，但检索结果生成使用明确标为synthetic的模拟输入；没有下载模型或伪称执行语义检索。

在仓库根生成独立合成数据并检查结构：

```sh
python -X utf8 skills/chemical-pfd-pid-cad/tools/drawing-knowledge/examples/create_demo.py --out outputs/synthetic-knowledge
python -X utf8 skills/chemical-pfd-pid-cad/tools/drawing-knowledge/engine/knowledge.py --data outputs/synthetic-knowledge assemble
python -X utf8 skills/chemical-pfd-pid-cad/tools/drawing-knowledge/engine/knowledge.py --data outputs/synthetic-knowledge validate
```

真实build/query/packet须另安装组件中的requirements-engine.txt，提供有许可的嵌入模型及含SHA的models/model.json，并导入自己有权使用的原件/卡片。公开示例的模型条目是不可用于语义建库的测试桩。Docling/OCR、可选PyMuPDF各自按依赖和许可说明配置；本次公开打包未重做全模型或OCR运行。

环境变量CHEM_KNOWLEDGE_DATA指定数据根，CHEM_KNOWLEDGE_ASSETS指定已审目录/字段资源，CHEM_KNOWLEDGE_CONFIG可指定运行JSON。默认不会搜索个人主目录中的私人知识库。模型权重与原件不应提交GitHub。

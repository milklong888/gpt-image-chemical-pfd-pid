# 原生文字度量包络定位

作者：milklong（GitHub：milklong888）。版权、MIT许可及第三方范围遵循所属Skill的ATTRIBUTION.md、LICENSE与既有来源声明。

这是原生度量定位工具，不是字墨轮廓、文字入框、字体正确性或工程设计验收器。它不绘图、不排版、不启动CAD，也不生成原生量测。接收已经取得的原生文字JSON及同一DWG回读DXF，先保留原生`GeometricExtents`。接触三角、框线或邻字仍应查看实际原生PDF笔画。

在所属Skill根目录调用：

```text
python tools/typography/native_text_envelopes.py --native-text review/native-text.json --readback-dxf review/readback.dxf --handle ABC --coordinate-space WCS --out review/envelope.json
python tools/typography/test_native_text_envelopes.py --json review/geometry-fixtures.json
```

输出目录须存在，已有输出不会覆盖。CLI只处理实际原生WCS包络对应的直接modelspace文字；JSON读取`native_text_extents`中的`handle/native_extents/rotation/actual_width/actual_height/location/raw_text`。项目调用方仍须绑定来源DWG、回读DXF与原生量测文件身份；哈希不证明量测来自正确图纸。

## 有限窄化与回退

默认输出保守原生分配框。仅在直接WCS、正常+Z平面、零旋转、正向水平流、TopLeft或TopRight、原生Location与实际对齐边相符、ActualHeight与原生分配高度一致时，才允许选择用ActualWidth缩窄。rotation/location须为明确有限数值，非法值回退保守框；非有限块矩阵或变换结果拒绝。还须通过`--simple-line-evidence`传入实际单行已审证据：`verified_single_line=true`、原生文件摘要`native_text_file_sha256`、`handle`、精确DXF/API文字摘要`dxf_raw_sha256/native_raw_sha256`及`format_profile`。该证据由实际原生审阅提供，工具不会自动编造。

`plain_single_line`仅接收无格式单行文本；`verified_one_font_span`仅接收该精确原生证据已覆盖的单一字体span。Unicode控制/格式字符（Cc/Cf）与行/段分隔（Zl/Zp）整体保守回退，不解释双向或零宽格式。复杂段落对齐/缩进、列、竖排/反向、未知/多段内联格式、多行、异常DefinedHeight均回退保守原生包络。不能用证据标签强行绕过格式限制。已记录同案原生实证只覆盖其具体单行TopLeft/TopRight输入，不推广到任意MTEXT。

居中、旋转及块变换测试只是有界几何机制测试；这些输入不因此获得通用原生支持。库函数`native_world_allocation(..., coordinate_space='BLOCK_LOCAL', block_transform=...)`仅接受有限仿射矩阵并保守转换明确局部AABB一次；非仿射、缺空间/变换或给已是WCS的包络重复变换会拒绝。它不重建实际旋转/块内字墨。

库调用`native_text_envelope(record, entity, coordinate_space='WCS')`返回`(Shapely包络, 元数据)`，包括实际对齐、选择方法、回退原因及窄化证据。不支持时保留保守框并检查实际PDF/补取原生证据，不从Location或指定Width猜一个较窄框，不放宽项目内边距或缩字。

测试保留15项原有机制场景，增加格式/方向/列/证据回退反例；全部是合成夹具和离线CLI测试，独立的右对齐预期会拒绝旧“始终向右”公式。测试通过不等于字体、字墨、工艺或工程批准。

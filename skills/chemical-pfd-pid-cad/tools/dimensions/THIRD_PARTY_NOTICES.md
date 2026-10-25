# 第三方来源与复用范围

本模块借鉴 `kasc0206/dwg-reader-skill` 的“按尺寸类型分类，集中输出读取事实”组织方式，独立写成薄审计层。固定提交：`8b04d54231700a0131073639ca0da02e20e45391`。

- [原读取脚本](https://github.com/kasc0206/dwg-reader-skill/blob/8b04d54231700a0131073639ca0da02e20e45391/scripts/extract_dimensions.py)
- [原许可证](https://github.com/kasc0206/dwg-reader-skill/blob/8b04d54231700a0131073639ca0da02e20e45391/LICENSE)
- 原脚本 SHA256：`2fe1bc86192b2f54f66470d9f4953f3f5d48e4af33fd1e06e85fcef5cd5e1a00`
- 原许可证 SHA256：`9e12635588fb5756986a08cf9c1434f8eb7d452ad668fd45eefcf76f942882d0`
- 完整许可证原文保留为 `LICENSE.dwg-reader-skill`。

保留声明：Copyright (c) 2026 DWG Reader Skill contributors。MIT 许可。

没有照搬其数值读取、文字替换、nearest 几何推断或容错降级实现。修正其类型5/6倒置；原始文字和实际测量分开，显式读取源DIMSTYLE及override，不把附近几何叫作关联。其他候选库 `dxf-civil` 没有并入代码。

实际创建/读取/图形块和十进制格式化能力复用现有 ezdxf 1.4.3，没有安装包或复制一套 CAD 引擎。`format_text` 为本机内部API，运行版本和有效舍入验证被冻结在本次验证；升级后必须复验，不承诺任意版本兼容。

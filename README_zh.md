# ub2parser — Unbound 2 解析器

解析《战舰世界》（Мир кораблей）Unbound 2 UI 框架定义文件（`.unbound`）的 Python 库。将源文件转换为可检查、可修改的具体语法树，并能无损写回——注释、空白符与格式均保持原样。

已在游戏 UI 代码库的 579 个 `.unbound` 文件上完成验证。

## 支持的语法结构

- **定义**：`constant`、`element`、`css`、`macro`、`struct`
- **作用域与绑定**：`scope`、`var`、`event`、`bind`、`bindcall`、`sync`、`dispatch`
- **显示对象**：`sprite`、`tf`、`block`、`element`、`htile`、`vtile`
- **控制器与样式**：`controller`、`style`、`filters`、`args`、`extends`
- **值类型**：带单位的数字（`100px`、`50%`）、十六进制字面量（`0xFF0000`）、多行字符串、映射 `{}`、列表 `[]`、点分路径标识符（`SC.path.Value`）、函数调用语法

## 安装

```bash
pip install ub2parser
```

本地开发安装：

```bash
pip install -e .
```

## 使用

```python
from ub2parser import tokenize, parse, serialize

with open('my_ui.unbound', 'r', encoding='utf-8') as f:
    source = f.read()

tokens = tokenize(source)        # 词法分析
doc = parse(tokens)              # 构建 CST

# 遍历语法树
for d in doc.definitions:
    print(f"{d.def_kind} {d.name.name}")
    for child in d.body:
        print(f"  {type(child).__name__}")

# 序列化——始终与源文件逐字节一致
result = serialize(doc, tokens)
assert source == result
```

## 命令行

```bash
# AST 结构概览
python -m ub2parser parse file.unbound
python -m ub2parser parse file.unbound -v

# 验证文件或目录
python -m ub2parser validate file.unbound
python -m ub2parser validate --all examples/

# 往返保真测试
python -m ub2parser roundtrip file.unbound

# 查看 token 流
python -m ub2parser tokens file.unbound
```

## 架构

处理管线分为三个阶段：

1. **Tokenizer** — 将源文本转换为平铺的 token 流，每个字节均被保留：结构标记、值字面量、空白符、换行符与注释全部记录。
2. **Parser** — 递归下降解析器，构建具体语法树（CST），每个节点记录其在 token 流中的起止位置。
3. **Serializer** — 按文档序遍历 CST，重放原始 token，生成的输出与输入逐字节一致。

## AST 节点参考

每个顶层定义对应一个 `DefNode`，包含 `def_kind` 字段（`"constant"`、`"element"`、`"css"`、`"macro"` 或 `"struct"`）、`name` 和 `body` 列表。

解析器产生的专用节点类型：

| 节点 | 对应语法 |
|------|----------|
| `Property` | `(width = 100px)` |
| `ScopeNode` | `(scope ...)` |
| `VarDecl` | `(var name:type = expr)` |
| `EventDecl` | `(event name)` |
| `BindNode` | `(bind target "source")` |
| `BindCallNode` | `(bindcall method ...)` |
| `DispatchNode` | `(dispatch event ...)` |
| `MacroCallNode` | `(macro Name ...)` |
| `DOMethod` | `(block ...)`、`(tf ...)`、`(sprite ...)` |
| `StyleNode` | `(style ...)` |
| `ControllerNode` | `(controller $Name ...)` |

所有节点均包含 `token_start` 与 `token_end` 索引，指向 token 列表中的位置，这是序列化器能够还原精确源文本的基础。

## 许可证

LGPL-3.0-only — 详见 [LICENSE](LICENSE)。

## 参考

- [Unbound 2 文档](https://forum.korabli.su/topic/127231-ub2-%D0%B4%D0%BE%D0%BA%D1%83%D0%BC%D0%B5%D0%BD%D1%82%D0%B0%D1%86%D0%B8%D1%8F-%D0%BF%D0%BE-unbound-20/)（Korabley 论坛，俄文）
- [Unbound 2 宏](https://forum.korabli.su/topic/170024-ub2-%D0%BC%D0%B0%D0%BA%D1%80%D0%BE%D1%81%D1%8B/)

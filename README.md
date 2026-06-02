# RouteMapper v0.1.0

基于 Python + Cartopy + Matplotlib，从 JSON 配置文件生成高分辨率自驾路线图。

## 快速开始

### 安装依赖
```bash
pip install -r requirements.txt
```

### 生成路线图
```bash
python generate.py routes/nanjiang_config.json
```

输出到 `~/Desktop/` 和 `~/.hermes/cache/documents/`。

### 可用路线
- `nanjiang` — 南疆丝路14天
- `beijiang` — 北疆大环线
- `xian` — 晋陕古建之旅
- `laojunshan` — 北京→老君山→开封

## 项目结构
```
├── generate.py          # 主入口
├── config.py            # 配置加载/验证
├── layout.py            # 布局引擎
├── renderer.py          # 渲染引擎
├── requirements.txt     # 依赖
├── routes/              # 路线JSON配置
└── README.md
```

## 配置格式

见 `routes/_template.json`。

## 命令行
```bash
python generate.py <config.json>     # 生成单条路线
python generate.py --all             # 生成全部路线
python generate.py --list            # 列出可用路线
python generate.py <config.json> -o <output.png>  # 指定输出路径
```

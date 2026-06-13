[AGENTS.md](https://github.com/user-attachments/files/28907972/AGENTS.md)
# -Tag-Manager-
这是一个简单的标签管理器，你能用它管理自己的标签库，为Lora训练数据集打标并编辑标签/This is a simple tag manager. You can use it to manage your own tag library, label datasets for Lora training, and edit tags.
# 标签工具 v1.0 — 数据集标注与标签管理工具

基于 Python Tkinter 的桌面工具，集成了**提示词库**、**WD14 数据集标注**和**数据集标签编辑器**三大功能模块。

## 功能概览

### 1. 提示词库
- 图片+提示词卡片瀑布流矩阵展示
- 支持多子库分类管理
- 一键 Google 翻译提示词及备注
- 双击编辑卡片，支持无限动态备注

### 2. 数据集标注（🏷️）
- 选择图片文件夹，批量生成 WD14 标签
- 支持 10 种标注模型：wd-vit-v3、wd-convnext-v3、wd-swinv2-v3 等
- ONNX Runtime 推理，优先 GPU（CUDA），自动回退 CPU
- 可调阈值、排除标签、附加标签、下划线转空格等
- 进度条+运行日志，后台线程不阻塞 UI，支持随时取消

### 3. 标签编辑器（✏️）
- 三列布局：图片网格 | 当前图片标签 | 全部标签计数
- 标签列表使用 Treeview 表格，显示标签名、出现次数、中文翻译
- 选中标签后点击顶部按钮删除（当前图片 或 全部图片）
- 自定义标签插入（弹出位置选择窗口，支持键盘输入位置）
- 搜索过滤三列同步刷新
- 全部替换、去重批量操作
- **修改不立即生效**，统一点击"保存所有修改"写入磁盘

## 项目结构

```
main.py                     # 主入口，UltimatePaletteApp 类
tagger/                     # WD14/CL 标注模块（ONNX 推理）
  interrogator.py           # 标注调度、模型注册、批量处理、依赖检查
  interrogators/
    base.py                 # Interrogator 基类 + 标签后处理
    wd14.py                 # WaifuDiffusionInterrogator（WD14 v2/v3）
    cl.py                   # CLTaggerInterrogator
  dbimutils.py              # 图像预处理（square/resize，纯 numpy+pillow）
  format.py                 # 输出文件名格式化
editor/                     # 标签编辑器模块
  tag_database.py           # TagDatabase 类，加载 danbooru.csv + e621.csv（200K 标签）
  auto_complete.py          # AutoCompleteEntry 控件，标签前缀匹配 + 中文翻译提示
  translation.py            # 加载 Translations/zh-CN.txt
data/                       # 数据文件
  danbooru.csv              # 100K Booru 标签
  e621.csv                  # 100K e621 标签
  quality.txt               # 质量标签
  translations/zh-CN.txt    # 5016 条中英标签翻译
models/                     # 标注模型下载缓存目录（自动下载）
```

## 依赖与安装

### 推荐安装方式

```bash
# 1. 克隆项目
git clone <repo-url>
cd project_1

# 2. 安装依赖
pip install Pillow numpy pandas onnxruntime huggingface_hub

# 可选：Google 翻译提示词功能
pip install deep_translator
```

### GPU 加速（可选）

如需 GPU 标注推理，安装 GPU 版 onnxruntime：

```bash
pip uninstall onnxruntime -y
pip install onnxruntime-gpu
```

### 依赖说明

| 包 | 用途 | 必需 |
|----|------|------|
| Pillow | 图片处理、缩略图 | 是 |
| numpy | 标注模型数值运算 | 标注功能必需 |
| pandas | 读取模型标签 CSV | 标注功能必需 |
| onnxruntime | WD14 模型 ONNX 推理 | 标注功能必需 |
| huggingface_hub | 下载标注模型 | 标注功能必需 |
| deep_translator | Google 翻译提示词 | 否（仅提示词库翻译功能需要） |

## 启动

```bash
python main.py
```

## 注意事项

- 提示词库数据保存在工作区目录的 `saved_prompts.json`
- 标注模型首次使用会自动从 HuggingFace 下载到 `models/` 目录
- 标签数据库（200K 标签）在程序启动时异步加载，不阻塞 UI
- 标注功能运行在后台线程，支持随时取消
- 数据集标签编辑器的修改不会立即写入磁盘，需点击"💾 保存所有修改"
- Windows 下建议使用 `python main.py` 直接运行，无需额外配置
- Linux/macOS 可能需要 `apt install python3-tk` / `brew install python-tk`

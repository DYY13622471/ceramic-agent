# 陶瓷建模学习智能体 (ceramic-agent)

**不是把操作录下来回放，而是把你的建模过程沉淀成"方法"，之后给个目标它自己建。**

你在 Rhino 里正常做一遍器型，它把命令序列、每个阶段的截图、你的意图记成一个"案例"；
本地大模型从案例里提炼出"这类器型是怎么做的"（造型 / 参数 / 工艺三段）；
下次你只说"建一个青花瓷瓶，满口 600ml，壁厚 2，高 210"，它就查方法库出方案、生成 Rhino 脚本、跑自检、不达标自己调参数重来。

全部本地闭环：本地模型、本地进程、本地文件，不上传任何数据。

## 它和"自动回放脚本"的区别

| | 回放型 | 本项目 |
| --- | --- | --- |
| 输入 | 固定脚本 | 目标描述（含尺寸） |
| 换一个器型 | 要重新录 | 查方法库直接出方案 |
| 错误处理 | 出错就停 | 量化自检 + 归因调参，迭代到达标 |
| 越用越强 | 不会 | 案例越多，方法库越贴合你自己的手法 |

## 三层结构

```
① 记录层 recorder/     你建模 → 命令序列 + 分阶段截图 + 意图 → 存成案例
② 学习层 learning/     从案例提炼方法 → 方法库（造型 / 参数 / 工艺）
③ 自主建模层 executor/  目标 → 查方法库出方案 → 生成 Rhino 脚本 → 自检 → 调参重试
```

## 环境要求

| 组件 | 说明 |
| --- | --- |
| Windows | 已在 Win11 + Rhino 8 上验证 |
| Rhino 8 | 需另装，本项目不附带 |
| Golem 插件 | Rhino 插件，提供 `127.0.0.1:9876` 本地 TCP 接口（场景读取 / 命令历史 / 截图 / 执行 Python）。**需自行安装，本项目不包含、不分发** |
| Python 3.11+ | 主流程纯标准库，无需 pip 装包 |
| Ollama | 本地 LLM 服务 `127.0.0.1:11434`，推荐模型 `qwen2.5:7b` |
| yt-dlp / faster-whisper | 仅"从音视频自学"分支需要，见 `requirements.txt` |

## 安装

```bash
git clone <本仓库地址> ceramic-agent
cd ceramic-agent

# 1. 本地模型（一次）
ollama pull qwen2.5:7b

# 2. 可选：从音视频自学才需要
pip install -r requirements.txt
```

Golem 插件装好后，启动 Rhino 即自动监听 `9876`。用这个命令确认通了：

```bash
python -c "from recorder.golem_client import GolemClient; print(GolemClient().ping())"
```

## 快速开始

```bash
# ① 记录一次建模（Rhino 开着，这个窗口别关）
python main.py record start

#    你按自己的习惯建完一段，就拍一步（隔几步拍一次即可，不用每步都拍）
python main.py record shot

#    建完后收尾，写一句意图——这句意图决定它以后怎么归类
python main.py record end --intent "汾杏青花瓷瓶 高210 壁厚2"
```

```bash
# ② 学习方法（本地模型提炼，几十秒到几分钟）
python main.py learn
```

```bash
# ③ 自主建模：只出方案 + 生成脚本
python main.py model "建一个青花瓷瓶 满口600ml 壁厚2 高210"

#    出方案 + 生成脚本 + 自动执行 + 自检 + 调参重试
python main.py model "建一个青花瓷瓶 满口600ml 壁厚2 高210" --auto
```

第 ③ 步成功后，脚本落在 `generated/`，可直接在 Rhino 的 ScriptEditor 里打开运行，也可以由 `--auto` 经 Golem 直接执行。

图形界面版（粘链接那种批量学习）在 `gui_launcher.py`：`python gui_launcher.py`。

## 命令一览

| 命令 | 作用 |
| --- | --- |
| `record start` | 开始记录会话，之后的操作进案例 |
| `record shot` | 拍一步（命令历史 + 当前视图截图） |
| `record end --intent "…"` | 结束并落盘成案例 |
| `learn` | 读全部案例，提炼/更新方法库 |
| `model "<描述>"` | 查方法库 → 生成方案与 Rhino 脚本 |
| `model "<描述>" --auto` | 加成自动执行 + 量化自检 + 归因调参闭环 |
| `python learning/bili_learn.py --local <文件>` | 从本机音视频自学一条方法 |

## 目录结构

```
ceramic-agent/
├── main.py                  入口：record / learn / model
├── gui_launcher.py          图形界面（批量学习用）
├── 一键启动记录器.bat        双击即可开始记录（可改 Python 路径）
├── recorder/                Golem TCP 客户端、记录器、自动分段
├── learning/                案例库、方法库、本地 LLM 客户端、音视频自学
├── executor/                规划器、脚本生成、自检、调参闭环
├── store/                   运行数据（案例、方法库、截图），仓库里只留空目录
│   ├── cases/               案例 JSON + 分阶段截图（本地生成，不入库）
│   └── method_library.json  方法库（本地生成，首次运行自动建默认库）
├── generated/               生成的 Rhino 脚本输出目录
├── examples/                已有的成品截图与生成脚本样例
├── requirements.txt
└── LICENSE
```

`store/` 默认是空的，第一次 `learn` 或 `model` 会自动建默认方法库，不会报错。

## 方法库是怎么长起来的

- 每个案例 = `command_sequence`（你在 Rhino 里敲的命令）+ `shots`（每步截图）+ `intent`（你写的意图）。
- `learn` 把同类意图聚合，交给本地模型提炼成三个字段：造型方法、关键参数、工艺约束。
- 语义去重（向量余弦）会跳过和已有方法过于相似的新条目，避免库被重复案例灌水。
- 起草的方案会带溯源 `source`，能查回是哪个案例 / 哪个视频学来的。

## 陶瓷工艺自检清单

内置 `executor/self_check.py` 会检查实体性、有效性、尺寸与体积。上机前请人工再核一遍：

```
① 壁厚 ≥ 2.0mm
② 流形、无破洞、封闭
③ 开模拔模 3~5°
④ 浮雕凹槽 ≥ 0.6mm，凸起 ≥ 0.8mm
⑤ 法线朝外，STL 二进制，公差 0.01
⑥ 灰度图 8~16 位，无爆黑爆白
```

自检通过不等于能烧：收缩率、釉面吸附、接坯强度这些工艺参数仍需你自己判断。

## 从音视频自学（可选分支）

`learning/bili_learn.py` 能把一条教程的语音转成逐字稿，再让本地模型提炼成方法入库：

```bash
python learning/bili_learn.py --local "D:\videos\拉坯教学.mp4"
python learning/bili_learn.py --urls "https://www.bilibili.com/video/BVxxxxxx"
```

**使用边界（请认真读）**：远程下载只用于处理你本人拥有权利、或已获授权的素材。第三方视频的逐字稿与音轨属于他人版权内容，请勿随仓库分发；本项目仓库不包含任何第三方转录稿与音轨。使用前请遵守对应平台的服务条款。

## 已知限制

- 生成脚本以回转类器型（瓶 / 罐 / 碗 / 杯 / 高足杯）为主；带流、把、提梁、异形开光类仍需手工建模。
- 依赖 Golem 插件，而 Golem 的接口无公开文档，本项目只按实测行为调用；Golem 升级后可能需要对 `recorder/golem_client.py` 做适配。
- 本仓库没有 Rhino 环境下的自动化测试，`self_check` 的判定逻辑靠案例回归，不保证覆盖全部器型。
- 记录层依赖你在 Rhino 里的命令历史；用界面拖拽、纯鼠标操作的部分无法完整还原。

## 许可证与商标

代码采用 MIT 许可证，见 `LICENSE`。可商用、可闭源衍生，保留版权声明即可。

Rhino / Grasshopper 是 McNeel 的商标，Golem 是其各自权利人的产品，Ollama、Qwen 同理。
本项目与上述公司/产品无任何隶属或背书关系，仅做本地兼容调用；相关软件需你自行取得合法授权。

## 贡献

带案例比带描述有用：在 Issue 里附上 `store/cases/xxx/case_*.json`（去掉截图）和一句意图，说明你期望它学成什么样。

<a id="top"></a>

# 圆球秘境 · 寻宝 | Round World: Treasure Hunt

> 一个用 **Python + ursina (Panda3D)** 写的**第三人称视角 3D 寻宝小游戏**。整个世界由一颗颗紫色光滑圆球铺成，**零外部美术 / 音频资源**：模型、音效、BGM、天气环境音全部在运行时程序化生成。
>
> A **third-person 3D treasure-hunt mini game** built with **Python + ursina (Panda3D)**. The world is paved with glossy purple spheres and ships with **zero external art or audio assets** — every mesh, sound effect, music loop and weather ambience is generated procedurally at runtime.

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB)](https://www.python.org/)
[![ursina](https://img.shields.io/badge/ursina-5.2.0-orange)](https://github.com/pokeapi/ursina)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)](#top)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

**语言 / Language：[中文](#中文) · [English](#english)**

---

## 中文

**目录**：[项目概述](#项目概述) · [玩法目标](#玩法目标) · [快速开始](#快速开始) · [操作方法](#操作方法) · [玩法提示](#玩法提示) · [天气系统](#天气系统) · [命令行参数与环境变量](#命令行参数与环境变量) · [项目结构](#项目结构) · [技术要点](#技术要点) · [自检模式](#自检模式) · [常见问题](#常见问题) · [许可证](#许可证)

### 项目概述

`圆球秘境 · 寻宝` 是一个克隆下来就能直接跑的 3D 小游戏：全部逻辑集中在单文件 `game.py`（约 2800 行），主打 **"程序化生成 + 轻松探索"**——没有血腥、没有失败惩罚、没有需要下载的资源包。

| 特性 | 说明 |
| --- | --- |
| 引擎 | Python 3.9+ / ursina 5.2.0（Panda3D） |
| 视角 | **第三人称轨道镜头**：鼠标绕角色环视，角色始终背对镜头、由你操控前进 |
| 世界 | 25 × 25 紫色圆球地面 + 更深更宽的地下洞穴，浮空平台 / 宝藏坐标等比放大 |
| 穿梭 | 按 `F` 在 **地面 ⇄ 地下洞穴** 之间下潜 / 上浮，镜头自动换层并淡入淡出 |
| 战斗 | 主人公的**圆头剑**（剑尖是一颗发光圆球）；妖怪只随机缓慢游荡，**不追人、不伤人**，命中 3 次消失 |
| 难度 | **没有血条**，玩家不会受伤，纯探索向，可以放心乱逛 |
| 天气 | 晴 / 雨 / 雪 / 风四种，随机切换；**任何天气下天空都是蓝天白云** |
| 资源 | 零外部素材：模型把光照**烘焙进顶点色**（无灯光、无 shader），音频用标准库 `wave` 合成 |
| 性能 | 约 1900 个实体，垂直同步下稳定 60 FPS |

### 玩法目标

在三个区域里找齐 **12 颗宝石**即胜利，结算界面会显示用时与击杀妖怪数：

| 区域 | 宝石数 | 怎么拿 |
| --- | --- | --- |
| 天上 | 4 | 踩场地角落的**粉色弹弹球**飞天，或沿 5 层浮空平台配合**二段跳**逐级爬上去 |
| 地面 | 3 | 走过去即可拾取 |
| 地下洞穴 | 5 | 3 颗摆在明处，2 颗藏在**发光冰晶**里，挥剑敲 2 下碎裂后取出 |

地面上还散布着若干**棕色土球**，敲碎只有粒子特效，属于纯装饰性彩蛋；妖怪不计入通关条件，想打想躲都可以。

### 快速开始

**环境要求**：Python **3.9+**；macOS / Windows / Linux；首次运行需要联网安装依赖。

**① 一键启动（推荐）**

```bash
# macOS / Linux
./start.sh

# Windows：双击 start.bat，或在命令行中运行
start.bat
```

macOS 用户也可以直接双击 `start.command`。脚本会自动：创建 `.venv` 虚拟环境 → 安装 `requirements.txt` 依赖 → 启动 `game.py`。依赖装好后会在 `.venv/.requirements.stamp` 打标记，二次启动秒进游戏；`requirements.txt` 变化时会自动重装。

**② 手动启动**

```bash
cd round_world
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt     # Windows: .venv\Scripts\pip
.venv/bin/python game.py                      # Windows: .venv\Scripts\python
```

**依赖**：`ursina==5.2.0`、`Pillow>=9.0`、`numpy>=1.20`、`screeninfo>=0.8`；macOS 上额外安装 `pyobjc-framework-Cocoa`（用于隐藏 / 回拉鼠标指针）。

> * 默认是**带标题栏的窗口模式**（1280 × 720），点窗口右上角关闭按钮即可退出；需要全屏见下方 `RW_FULLSCREEN`。
> * 首次启动会在 `assets/sounds/` 自动生成 20 个程序化合成的 WAV（音效 + 12 秒循环 BGM + 雨 / 风 / 雪 / 雷环境音），无需下载任何资源。

### 操作方法

进入游戏后，**鼠标**负责转动第三人称镜头，键盘负责移动与交互：

| 按键 | 作用 |
| --- | --- |
| 鼠标移动 | 绕角色转动镜头（左右 0.16°/像素、上下 0.15°/像素，可用 `RW_MOUSE_SENS` 调整） |
| `W` / `S` | 前进 / 后退 |
| `A` / `D` | 左移 / 右移 |
| `Shift` | 奔跑（移动速度 6.0 → 9.0） |
| `空格` | 跳跃 / **二段跳**（二段跳明显蹿得更高） |
| `鼠标左键` / `J` | 挥圆头剑攻击（判定宽松：贴身必中，前方大扇形也能命中） |
| `F` | 下潜进入地下 / 从地下上浮（穿梭） |
| `1` `2` `3` `4` | 手动切换天气：晴 / 雨 / 雪 / 风 |
| `T` | 循环切换到下一种天气 |
| `P` / `Esc` | 暂停 / 继续 |
| `R` | 重新开始（游戏中 / 暂停中 / 结算界面都可以） |
| `Q` | 退出游戏（标题 / 暂停 / 结算界面；也可直接点窗口关闭按钮） |

界面类操作：

| 界面 | 操作 |
| --- | --- |
| 标题界面 | 点击鼠标，或按 `空格` / `回车` / `W` / `J` 开始；`Esc` 退出 |
| 暂停界面 | `P` / `Esc` 继续，`R` 重新开始，`Q` 退出 |
| 胜利界面 | `R` 再玩一次，`Q` / `Esc` 退出 |

**HUD 布局**：左上角 = `宝藏 x/12 · 击杀 n · 用时`；右上角 = `当前层（地面 / 地下）· FPS · 天气`；底部 = 当前场景对应的按键提示；天气变化时屏幕上方会飘一条提示。

### 玩法提示

* **飞天**：场地角落有**粉色弹弹球**，踩上去会被高高弹起，是够天上宝石最快的方式；
* **爬平台**：5 层浮空平台高度递增，配合二段跳可以一路爬到最高处；
* **地下**：按 `F` 下潜后，洞穴里有发光水晶与萤光灯，敲碎冰晶（2 下）取出宝石，再按 `F` 上浮回地面；
* **妖怪**：不会追人也不会伤人，命中 3 次消失；不打它们也完全不影响通关；
* **看天**：把镜头往上抬（仰视上限 42°）可以看到云层、雨幕、雪花与闪电；
* **穿梭时**：镜头会自动拉近 / 换层并淡入淡出，期间按键无效，等提示恢复即可。

### 天气系统

世界里有 **晴天 / 下雨 / 下雪 / 刮风** 四种天气，每 24 ~ 55 秒随机换一种，切换时约 2.8 秒平滑过渡（雨转雪会短暂两种同框）。所有表现均为程序化生成，**不用 shader、不用灯光**：

| 天气 | 表现 |
| --- | --- |
| 晴天 `clear` | 太阳 + 光晕、星星最亮、云最淡，天空偏暖 |
| 下雨 `rain` | 相机空间滚动雨幕（2 层）+ 世界空间雨丝 + 落地涟漪 + 随机**闪电**（屏幕闪白 + 合成闷雷） |
| 下雪 `snow` | 慢慢飘落、左右摇摆的雪花，环境音是轻柔的雪风声 |
| 刮风 `wind` | 横向风丝 + 飞尘、云被吹着跑、脚边小球像草一样摆、镜头轻微侧倾抖动、腾空时被风推着偏移；带阵风与缓慢游走的风向 |

细节：

* **天空在任何天气下都是蓝色渐变 + 白云**，下雨只是叠一层很淡的冷色调；
* 下潜到**地下洞穴**后降水清空、环境音变闷、天空色调撤掉，上浮回来再恢复；
* 右上角 HUD 实时显示当前天气；
* 雨 / 风 / 雪环境音与雷声都是启动时用标准库合成的**无缝循环 WAV**；
* 想固定某种天气（调试 / 截图）：设 `RW_WEATHER=rain|snow|wind|clear`，或 `./start.sh --weather rain`。

### 命令行参数与环境变量

启动脚本参数（`start.sh` / `start.bat` / `start.command` 通用；未识别的参数原样透传给 `game.py`）：

| 参数 | 作用 |
| --- | --- |
| `--selftest` | 自检模式：自动玩一遍并截图，约 13 秒后自动退出 |
| `--weather <kind>` | 锁定天气启动：`clear` / `rain` / `snow` / `wind` |
| `-f` / `--force` | 强制重新安装依赖 |
| `-h` / `--help` | 查看帮助 |

环境变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `RW_FULLSCREEN` | 空（窗口模式） | 设为 `1` 时全屏启动 |
| `RW_MOUSE_SENS` | `1.0` | 鼠标灵敏度，有效范围 0.2 ~ 4.0 |
| `RW_WEATHER` | 空（随机） | 锁定天气：`clear` / `rain` / `snow` / `wind` |
| `RW_SELFTEST` | 空 | 设为 `1` 进入自检模式（等价于 `--selftest`） |

示例：

```bash
RW_FULLSCREEN=1 RW_MOUSE_SENS=1.6 ./start.sh      # 全屏 + 更高灵敏度
RW_WEATHER=snow ./start.sh --selftest             # 锁定雪天跑自检截图
```

### 项目结构

```
round_world/
├── game.py             # 全部游戏逻辑（单文件，约 2800 行）
├── requirements.txt    # 依赖清单
├── start.sh            # macOS / Linux 一键启动脚本
├── start.command       # macOS 双击入口（转发给 start.sh）
├── start.bat           # Windows 一键启动脚本
├── assets/sounds/      # 首次运行自动合成的 20 个 WAV（音效 / BGM / 天气环境音）
├── README.md           # 本文档（中英双语）
└── LICENSE             # MIT 许可证
```

`game.py` 内部按注释分段：调色板 → 程序化音效合成 → PIL 中文文字贴图 → 程序化网格 → 粒子 / 天气 → 世界常量与关卡布局 → 实体（宝石 / 妖怪 / 可破坏物 / 主人公）→ 相机 → HUD → 输入 → 主循环 → 自检 → 启动入口。

### 技术要点

* **零外部美术资源**：所有模型（圆球地面 / 第三人称圆头小人 / 圆头剑 / 妖怪 / 宝石 / 刀光 / 天空穹顶…）都是运行时程序化生成的网格，并把光照**烘焙进顶点色**，因此不需要灯光与 shader，约 1900 个实体仍稳定 60 FPS；
* **第三人称轨道镜头**：机位沿"角色 → 镜头"轨道线做碰撞回缩（撞地面 / 洞顶 / 场墙自动拉近）；角色背面用帽子 + 背包做方位线索、正面用凸眼 + 嘴做脸，朝向一目了然；
* **自管鼠标视角**：不用 ursina 的 `mouse.locked`（Panda3D 异步切换模式会导致视角乱晃 / 抖动），改为常驻绝对模式、自己累加每帧像素位移，指针接近窗口边缘时回拉到中心并改以中心为基准——不丢位移、不跳变、可以一直转下去；
* **零外部音频资源**：音效、12 秒循环 BGM 与天气环境音（雨 / 风 / 雪 / 雷）全部由标准库 `wave` + `struct` 合成；
* **天气系统零 shader / 零灯光**：穹顶颜色倍率 + 内层半透明天空罩 + 相机前全屏色调层调气氛；降水 / 飞尘用 billboard 粒子池（260）+ 落地涟漪（18）+ 两层相机空间滚动雨幕；
* **中文 HUD**：用 Pillow + 系统中文字体（自动探测 PingFang / Hiragino Sans GB / Arial Unicode / STHeiti / 微软雅黑 / Noto Sans CJK）渲染成贴图挂在 `aspect2d` 上；
* 穿梭、二段跳、弹弹球、平台落地、怪物随机游荡、粒子池等均为手写轻量物理 / 逻辑，没有引入物理引擎。

### 自检模式

用于无人值守验证，也方便一次性截出各种画面：

```bash
./start.sh --selftest
# 等价于：RW_SELFTEST=1 .venv/bin/python game.py
```

它会自动开局、走位、跳跃、二段跳、攻击、下潜 / 上浮、拾取、触发胜利界面，中途依次切换四种天气（含抬头看天的镜头），并把过程截图保存到 `/tmp/rwtest/play_*.png`（`play_rain_*` / `play_snow_up` / `play_wind` / `play_e` 对应四种天气）。

收尾阶段还会自动验证三件事并把结果打印到日志：

* **鼠标视角**：程序化地每帧移动指针 14 像素、共 12 帧，检查镜头转角是否精确等于 `12 × 14 × 灵敏度`（日志出现 `MOUSELOOK ... err=0.000` 即通过）；
* **暂停后重开**：暂停中按 `R` 必须能干净地重开一局（`RESTART-FROM-PAUSE ... state=play`）；
* **暂停中退出**：暂停中按 `Q` 必须能真正退出进程（`GAME QUIT`，进程退出码 0）。

全程约 13 秒后自动退出。

### 常见问题

**Q：提示 `ModuleNotFoundError: No module named 'ursina'`？**
A：说明用的不是项目虚拟环境里的 Python。优先用 `./start.sh`（Windows：`start.bat`），或确认执行的是 `.venv/bin/python game.py`（Windows：`.venv\Scripts\python.exe game.py`）。依赖装坏了可以 `./start.sh -f` 强制重装。

**Q：macOS 双击 `start.command` 打不开 / 提示无法验证开发者？**
A：在终端执行 `chmod +x start.command` 后再双击，或右键 → 打开；也可以直接在终端运行 `./start.sh`。

**Q：HUD 中文变成方框（豆腐块）？**
A：程序会依次探测 PingFang（macOS）、Hiragino Sans GB、Arial Unicode、STHeiti、微软雅黑（Windows）、Noto Sans CJK（Linux）；都没找到时退回 PIL 默认字体（不含中文字形）。Linux 上安装 `fonts-noto-cjk` 即可解决。

**Q：没有声音？**
A：音效在首次启动时合成到 `assets/sounds/`。如果第一次启动被中断，删除该目录下的 WAV 再启动一次即可重新生成；同时检查系统音量与输出设备。

**Q：鼠标转视角太快 / 太慢？**
A：用 `RW_MOUSE_SENS` 调整，例如 `RW_MOUSE_SENS=0.6 ./start.sh`（有效范围 0.2 ~ 4.0）。

**Q：帧率偏低？**
A：游戏默认开启垂直同步、目标 60 FPS。可以缩小窗口、关闭其他占用 GPU 的程序；粒子池与雨幕层数都是代码常量，必要时可在 `game.py` 里调小（`Particles(n=150)`、天气粒子池 `n=260`、`RainSheets.LAYERS`）。

**Q：怎么退出游戏？**
A：在标题 / 暂停 / 结算界面按 `Q`，或直接点窗口右上角的关闭按钮。游戏进行中按 `Q` 不会退出（防误触），需要先按 `Esc` 暂停。

### 许可证

本项目基于 **MIT License** 开源，完整条款见 [LICENSE](LICENSE)。

游戏本身不包含任何第三方美术 / 音频素材（全部运行时程序化生成）。运行时依赖的 [ursina](https://github.com/pokeapi/ursina)、[Pillow](https://python-pillow.org/)、[NumPy](https://numpy.org/)、[screeninfo](https://github.com/rr-/screeninfo)、[pyobjc](https://github.com/ronaldoussoren/pyobjc) 各自遵循其自身的开源许可证。

[↑ 回到顶部 / Back to top](#top)

---

## English

**Contents**: [Overview](#overview) · [Objective](#objective) · [Quick Start](#quick-start) · [Controls](#controls) · [Gameplay Tips](#gameplay-tips) · [Weather System](#weather-system) · [CLI Flags & Environment Variables](#cli-flags--environment-variables) · [Project Layout](#project-layout) · [Technical Notes](#technical-notes) · [Self-Test Mode](#self-test-mode) · [FAQ](#faq) · [License](#license)

### Overview

*Round World: Treasure Hunt* is a 3D mini game you can clone and run immediately. All of the logic lives in a single file, `game.py` (~2,800 lines), and the design goal is **"everything procedural + relaxed exploration"** — no gore, no fail states, no asset packs to download.

| Feature | Details |
| --- | --- |
| Engine | Python 3.9+ / ursina 5.2.0 (Panda3D) |
| Camera | **Third-person orbit camera**: the mouse circles around the character, who always has their back to the camera |
| World | 25 × 25 field of purple spheres + a deeper, wider underground cave; floating platforms and treasure coordinates scale proportionally |
| Traversal | Press `F` to **dive down to the cave / rise back to the surface**; the camera switches layers with a fade |
| Combat | The hero wields a **round-headed sword** (its tip is a glowing sphere). Monsters wander slowly, **never chase and never hurt you**, and vanish after 3 hits |
| Difficulty | **No health bar** — the player cannot be damaged, so exploration is completely stress-free |
| Weather | Four states (clear / rain / snow / wind) that switch randomly; **the sky stays blue with white clouds in every one of them** |
| Assets | Zero external assets: lighting is **baked into vertex colours** (no lights, no shaders), audio is synthesised with the stdlib `wave` module |
| Performance | ~1,900 entities at a steady 60 FPS with vsync on |

### Objective

Collect all **12 gems** spread across three areas to win. The victory screen reports your time and the number of monsters defeated:

| Area | Gems | How to get them |
| --- | --- | --- |
| Sky | 4 | Bounce off the **pink trampoline ball** in a corner of the field, or climb the 5 floating platforms using the **double jump** |
| Surface | 3 | Simply walk into them |
| Underground cave | 5 | 3 are out in the open, 2 are sealed inside **glowing ice crystals** — hit them twice with the sword to break them open |

A few **brown dirt balls** are scattered on the surface; breaking them only produces particles (decorative easter eggs). Monsters are not required for completion — fight them or ignore them, your choice.

### Quick Start

**Requirements**: Python **3.9+**; macOS / Windows / Linux; an internet connection for the first run (to install dependencies).

**① One-command launch (recommended)**

```bash
# macOS / Linux
./start.sh

# Windows: double-click start.bat, or run it from a terminal
start.bat
```

On macOS you can also double-click `start.command`. The script creates a `.venv` virtual environment, installs the dependencies from `requirements.txt`, then launches `game.py`. Once installed, a marker is written to `.venv/.requirements.stamp` so subsequent launches go straight into the game; dependencies are reinstalled automatically whenever `requirements.txt` changes.

**② Manual launch**

```bash
cd round_world
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt     # Windows: .venv\Scripts\pip
.venv/bin/python game.py                      # Windows: .venv\Scripts\python
```

**Dependencies**: `ursina==5.2.0`, `Pillow>=9.0`, `numpy>=1.20`, `screeninfo>=0.8`; on macOS `pyobjc-framework-Cocoa` is also installed (used to hide / re-centre the mouse pointer).

> * The default mode is a **windowed, titled 1280 × 720 window** — use the window's close button to quit. See `RW_FULLSCREEN` below for fullscreen.
> * On first launch the game synthesises 20 WAV files into `assets/sounds/` (sound effects + a 12-second looping BGM + rain / wind / snow / thunder ambience). Nothing needs to be downloaded.

### Controls

In game, the **mouse** rotates the third-person camera while the keyboard handles movement and interaction:

| Key | Action |
| --- | --- |
| Mouse movement | Orbit the camera around the character (0.16°/px horizontally, 0.15°/px vertically; tunable via `RW_MOUSE_SENS`) |
| `W` / `S` | Move forward / backward |
| `A` / `D` | Strafe left / right |
| `Shift` | Run (movement speed 6.0 → 9.0) |
| `Space` | Jump / **double jump** (the double jump goes noticeably higher) |
| `Left mouse button` / `J` | Swing the round-headed sword (very forgiving hit detection: point-blank always lands, a wide forward arc also hits) |
| `F` | Dive into the cave / rise back to the surface |
| `1` `2` `3` `4` | Set weather manually: clear / rain / snow / wind |
| `T` | Cycle to the next weather |
| `P` / `Esc` | Pause / resume |
| `R` | Restart (works while playing, while paused, and on the result screen) |
| `Q` | Quit (title / pause / result screens; the window close button also works) |

Menu screens:

| Screen | Actions |
| --- | --- |
| Title | Click the mouse or press `Space` / `Enter` / `W` / `J` to start; `Esc` to quit |
| Pause | `P` / `Esc` resume, `R` restart, `Q` quit |
| Victory | `R` play again, `Q` / `Esc` quit |

**HUD layout**: top-left = `gems x/12 · kills · elapsed time`; top-right = `current layer (surface / cave) · FPS · weather`; bottom = contextual key hints; a toast appears at the top of the screen when the weather changes.

### Gameplay Tips

* **Flying**: the **pink trampoline ball** in a corner of the field launches you high into the air — the fastest way to reach sky gems;
* **Platforming**: the 5 floating platforms rise in steps; combine them with the double jump to reach the highest gem;
* **Underground**: press `F` to dive; the cave contains glowing crystals and lamp lights. Break an ice crystal (2 hits) to free the gem inside, then press `F` again to rise back up;
* **Monsters**: they neither chase nor damage you and disappear after 3 sword hits — skipping them entirely does not block completion;
* **Sky watching**: tilt the camera up (max 42° pitch) to see clouds, rain sheets, snowflakes and lightning;
* **While travelling**: the camera pulls in, switches layer and fades; input is ignored during the transition, just wait for the hint text to come back.

### Weather System

The world cycles through **clear / rain / snow / wind**. A new weather is picked at random every 24–55 seconds with a ~2.8 second cross-fade (rain → snow briefly shows both). Everything is procedural — **no shaders, no lights**:

| Weather | Presentation |
| --- | --- |
| Clear `clear` | Sun + glow halo, brightest stars, faintest clouds, warmer sky |
| Rain `rain` | Two camera-space scrolling rain sheets + world-space rain streaks + ground ripples + random **lightning** (white screen flash + synthesised thunder) |
| Snow `snow` | Slowly drifting, side-swaying snowflakes with a soft snowy-wind ambience |
| Wind `wind` | Horizontal wind streaks + flying dust, clouds blown along, ground spheres swaying like grass, slight camera roll/shake, airborne drift; includes gusts and a slowly wandering wind direction |

Details:

* **The sky is always a blue gradient with white clouds**; rain only adds a very faint cool tint on top;
* Once you dive into the **cave**, precipitation is cleared, ambience becomes muffled and the sky tint is removed — everything is restored when you rise back up;
* The current weather is shown in the top-right HUD;
* Rain / wind / snow ambience and thunder are **seamlessly looping WAV files** synthesised with the standard library at startup;
* To pin a weather (debugging / screenshots): set `RW_WEATHER=rain|snow|wind|clear`, or run `./start.sh --weather rain`.

### CLI Flags & Environment Variables

Launcher flags (shared by `start.sh` / `start.bat` / `start.command`; unrecognised arguments are passed through to `game.py`):

| Flag | Purpose |
| --- | --- |
| `--selftest` | Self-test mode: plays itself, takes screenshots, exits after ~13 seconds |
| `--weather <kind>` | Start with a pinned weather: `clear` / `rain` / `snow` / `wind` |
| `-f` / `--force` | Force a dependency reinstall |
| `-h` / `--help` | Show help |

Environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `RW_FULLSCREEN` | empty (windowed) | Set to `1` to start in fullscreen |
| `RW_MOUSE_SENS` | `1.0` | Mouse sensitivity, clamped to 0.2 – 4.0 |
| `RW_WEATHER` | empty (random) | Pin the weather: `clear` / `rain` / `snow` / `wind` |
| `RW_SELFTEST` | empty | Set to `1` for self-test mode (same as `--selftest`) |

Examples:

```bash
RW_FULLSCREEN=1 RW_MOUSE_SENS=1.6 ./start.sh      # fullscreen + higher sensitivity
RW_WEATHER=snow ./start.sh --selftest             # pinned snow weather while self-testing
```

### Project Layout

```
round_world/
├── game.py             # All game logic (single file, ~2,800 lines)
├── requirements.txt    # Dependency list
├── start.sh            # One-command launcher for macOS / Linux
├── start.command       # macOS double-click entry (forwards to start.sh)
├── start.bat           # One-command launcher for Windows
├── assets/sounds/      # 20 WAV files synthesised on first run (SFX / BGM / weather ambience)
├── README.md           # This document (bilingual)
└── LICENSE             # MIT license
```

Inside `game.py`, sections are separated by comment banners: palette → procedural audio synthesis → PIL Chinese text textures → procedural meshes → particles / weather → world constants and level layout → entities (gems / monsters / breakables / player) → camera → HUD → input → main loop → self-test → entry point.

### Technical Notes

* **Zero external art**: every model (sphere ground / third-person round-headed character / round-headed sword / monsters / gems / sword trail / sky dome…) is a procedurally generated mesh created at runtime, with lighting **baked into vertex colours** — so no lights and no shaders are needed, and ~1,900 entities still hold a steady 60 FPS;
* **Third-person orbit camera**: the camera position is resolved along the "character → camera" ray with collision pull-in (it automatically moves closer when it would hit the ground, the cave ceiling or the field walls). The character's back uses a hat + backpack as orientation cues and the front uses bulging eyes + a mouth, so the facing direction is always readable;
* **Hand-rolled mouse look**: ursina's `mouse.locked` is not used, because Panda3D switches pointer mode **asynchronously**, which makes the camera spin/jitter. Instead the pointer stays in absolute mode, per-frame pixel deltas are accumulated manually, and when the pointer approaches the window edge it is warped back to the centre with the centre taken as the new reference — no lost motion, no jumps, infinite rotation;
* **Zero external audio**: sound effects, the 12-second looping BGM and the weather ambiences (rain / wind / snow / thunder) are all synthesised with the standard library `wave` + `struct` modules;
* **Weather without shaders or lights**: atmosphere comes from a sky-dome colour multiplier + an inner translucent sky shell + a fullscreen tint quad in front of the camera; precipitation and dust use a billboard particle pool (260) + ground ripples (18) + two camera-space scrolling rain sheets;
* **Chinese HUD**: text is rendered with Pillow and a system CJK font (auto-detected among PingFang / Hiragino Sans GB / Arial Unicode / STHeiti / Microsoft YaHei / Noto Sans CJK) into textures attached to `aspect2d`;
* Traversal, double jump, the trampoline ball, platform landing, monster wandering and the particle pools are all hand-written lightweight physics/logic — no physics engine involved.

### Self-Test Mode

Useful for unattended verification, and for grabbing a batch of screenshots in one go:

```bash
./start.sh --selftest
# equivalent to: RW_SELFTEST=1 .venv/bin/python game.py
```

It automatically starts a run, walks around, jumps, double-jumps, attacks, dives / rises, picks gems up, triggers the victory screen, and cycles through all four weathers on the way (including camera angles that look up at the sky). Screenshots are written to `/tmp/rwtest/play_*.png` (`play_rain_*` / `play_snow_up` / `play_wind` / `play_e` cover the four weathers).

At the end it verifies three things and prints the results to the log:

* **Mouse look**: the pointer is moved programmatically by 14 pixels per frame for 12 frames and the resulting camera rotation must equal exactly `12 × 14 × sensitivity` (`MOUSELOOK ... err=0.000` means pass);
* **Restart from pause**: pressing `R` while paused must cleanly restart the run (`RESTART-FROM-PAUSE ... state=play`);
* **Quit from pause**: pressing `Q` while paused must actually terminate the process (`GAME QUIT`, exit code 0).

The whole pass takes about 13 seconds and then exits on its own.

### FAQ

**Q: `ModuleNotFoundError: No module named 'ursina'`**
A: You are not using the project's virtual environment. Prefer `./start.sh` (Windows: `start.bat`), or make sure you run `.venv/bin/python game.py` (Windows: `.venv\Scripts\python.exe game.py`). If the environment is broken, run `./start.sh -f` to force a reinstall.

**Q: macOS refuses to open `start.command` ("unidentified developer")**
A: Run `chmod +x start.command` in a terminal first, or right-click → Open, or simply run `./start.sh` from the terminal.

**Q: The Chinese HUD text shows up as boxes (tofu)**
A: The game probes PingFang (macOS), Hiragino Sans GB, Arial Unicode, STHeiti, Microsoft YaHei (Windows) and Noto Sans CJK (Linux) in order, and falls back to the default PIL bitmap font (which has no CJK glyphs). On Linux, install `fonts-noto-cjk`.

**Q: No sound**
A: Audio is synthesised into `assets/sounds/` on first launch. If that first launch was interrupted, delete the WAV files in that folder and start again to regenerate them. Also check the system volume and output device.

**Q: Mouse look is too fast / too slow**
A: Adjust it with `RW_MOUSE_SENS`, e.g. `RW_MOUSE_SENS=0.6 ./start.sh` (valid range 0.2 – 4.0).

**Q: Low frame rate**
A: Vsync is on by default and the target is 60 FPS. Try a smaller window and close other GPU-heavy applications. The particle pools and rain-sheet layers are plain constants in the code and can be reduced if needed (`Particles(n=150)`, the weather pool's `n=260`, `RainSheets.LAYERS`).

**Q: How do I quit?**
A: Press `Q` on the title / pause / result screen, or click the window's close button. `Q` is deliberately ignored during gameplay to avoid accidental exits — press `Esc` to pause first.

### License

This project is released under the **MIT License** — see [LICENSE](LICENSE) for the full text.

The game itself contains no third-party art or audio assets (everything is generated procedurally at runtime). The runtime dependencies [ursina](https://github.com/pokeapi/ursina), [Pillow](https://python-pillow.org/), [NumPy](https://numpy.org/), [screeninfo](https://github.com/rr-/screeninfo) and [pyobjc](https://github.com/ronaldoussoren/pyobjc) remain under their own open-source licenses.

[↑ Back to top / 回到顶部](#top)

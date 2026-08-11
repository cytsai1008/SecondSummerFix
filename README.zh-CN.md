# SecondSummerFix

[English](README.md) · **简体中文**

《A Second Chance to Relive Summer》（Ren'Py 引擎，Steam app **4309030**）的修复集合：
1.0 → 2.1.0 更新后存档打不开、Steam 云同步同步错了文件夹、Steam 成就永远不解锁，
以及在 CrossOver / Wine 下音频失真。

四个问题互相独立，按症状取用即可。

## 症状 → 修复

| 你看到的现象 | 修复 |
|---|---|
| 点存档格时崩溃，报 `Couldn't find a place to stop rolling back` | `tools/savefix.cmd fix` — [docs/saves.zh-CN.md](docs/saves.zh-CN.md) |
| 点存档格完全没反应 | 同上。存档签名失效了，`fix` 会重新签名。 |
| 两台机器存档不一致，或 Steam 云把旧存档盖回来 | `tools/make-junction.*` — [docs/saves.zh-CN.md](docs/saves.zh-CN.md#联接更好的做法) |
| Steam 成就永远不解锁 | 缺 `steam_api64.dll` — [docs/achievements.zh-CN.md](docs/achievements.zh-CN.md) |
| 音量极低、爆音、部分音效变调（macOS/Linux + Wine） | `wine/environment.txt` — [wine/README.zh-CN.md](wine/README.zh-CN.md) |

## 安装位置

把 `tools/` 整个复制到游戏安装根目录 —— 也就是同时含有 `CSE-1.0-pc\` 和
`CSE-2.1.0-pc\` 的那一层：

```
...\steamapps\common\CSE-1.0-pc\
    CSE-1.0-pc\
    CSE-2.1.0-pc\
    tools\            <- 放这里
```

`savefix.py` 靠扫描自己所在目录的上一层来定位游戏安装，放在别处运行会直接报
`no installed game found under <path>` 退出。

`wine/environment.txt` 是例外：它要放在每个 `.exe` 旁边，见
[wine/README.zh-CN.md](wine/README.zh-CN.md)。

## 文件清单

| | |
|---|---|
| `tools/savefix.py` `savefix.cmd` | 存档检查 / 修复工具。运行 `.cmd`，它会自动准备 `ecdsa` 依赖。 |
| `tools/make-junction.cmd` `.sh` | 把 Steam 云同步的文件夹指向游戏真正使用的那个。 |
| `wine/environment.txt` | 放到游戏 `.exe` 旁边，修复 Wine 音频。 |
| `docs/saves.zh-CN.md` | 存档为什么会坏、修复原理、存档位置、Steam 云、双机游玩。 |
| `docs/achievements.zh-CN.md` | 成就为什么是死的，以及 DLL 必须来自哪个 SDK 版本。 |
| `wine/README.zh-CN.md` | Wine 音频问题，以及解决它的两个设置。 |

`wine/` 下的内容只适用于用 Wine 或 CrossOver 跑 Windows 版；在 Windows 上直接忽略
该目录。其余部分各平台通用 —— 只是 `tools/make-junction.sh` 是
`make-junction.cmd` 在 Linux/macOS + Wine 下的对应版本，因为是同一个修复，所以放在
一起。

除路径外，这里的东西都不绑定具体版本：`savefix.py` 不写死任何版本号或偏移量，音频
修复对任何 Wine 下的 Ren'Py 游戏都有效。

## 安全性

- 不带参数的 `savefix` 是只读的。任何写入前都会自动备份。
- 存档和 `.rpyc` 都是 pickle 文件；工具从不把它们交给标准 unpickler，所以里面的
  内容无法执行。
- `steam_api64.dll` 只从官方 SDK 取，绝不要从破解版游戏里拿。

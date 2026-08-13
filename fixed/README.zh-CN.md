# 官方已修复 —— 仅作存档保留

[English](README.md) · **简体中文**

原本四个问题里的两个，已被 **2026 年 8 月 13 日的小型更新**修复（depot `4309031`，manifest `4957350886103385162`，build `24699923`，构建于 2026-08-12 18:59 UTC）。在该版本或更新的版本上，这个目录里的东西都用不到了；保留它们是给还停在旧版本的人，以及作为问题本身的记录。

| 原来的问题 | 官方怎么修的 | 这里保留的旧办法 |
|---|---|---|
| Steam 成就永远不解锁 | 游戏包里现在带了 `steam_api64.dll` | [achievements.zh-CN.md](achievements.zh-CN.md) |
| Steam 云同步的是旧的 `CSE-1.0-pc` 存档目录 | 云配置已改为指向 `CSE-2.1.0-pc\game\saves` | `make-junction.cmd` / `.sh` |

## 这次更新到底改了什么

manifest 里新增的文件正好只有两个 —— 之前缺失的 Steam 库：

```
+ CSE-2.1.0-pc\lib\py3-windows-x86_64\steam_api64.dll   319584 字节
+ CSE-2.1.0-pc\lib\py3-linux-x86_64\libsteam_api.so     388288 字节
```

Windows 那个 DLL 是 319584 字节，正是 [achievements.zh-CN.md](achievements.zh-CN.md) 里让你手动放进去的那个 Steamworks SDK 1.62 版本。如果你之前已经放好了，内容一致，Steam 不会动你那份。

云同步是服务器端的改动，本地没有任何文件能直接体现。看 `<Steam>\userdata\<accountid>\4309030\remotecache.vdf`：现在被跟踪的每一条都是 `CSE-2.1.0-pc/game/saves/...`，Steam 的 `steam_autocloud.vdf` 标记也写进了那个目录，`CSE-1.0-pc` 的路径一条都不剩。

## 如果你已经建了联接

留着或拆掉都行。它把旧目录指向当前目录，现在只是多余，并不会出错。要拆：关掉 Steam 和游戏，运行 `make-junction.cmd --undo`（或 `.sh --undo`）。这两个脚本仍然要和 `savefix` 一样，放在与 `CSE-2.1.0-pc\` 同级的安装根目录下。

## 没被修复的部分

- **1.0 → 2.1.0 打不开的存档**仍然要用 `tools/savefix` —— 见 [../docs/saves.zh-CN.md](../docs/saves.zh-CN.md)。这次更新又重新编译了脚本，但语句标识符保留了下来，所以 2.1.0 的存档照常能读。
- **Wine / CrossOver 音频**完全没动：`environment.txt` 不在 depot 里 —— 见 [../wine/README.zh-CN.md](../wine/README.zh-CN.md)。

# CrossOver / Wine 下音频失真

[English](README.md) · **简体中文**

## 症状

用 Wine（macOS 上的 CrossOver 瓶子）跑 Windows 版：部分音效音调不对。

Steam 上没有原生 Mac 或 Linux 版本，所以除了用 Ren'Py SDK 跑游戏之外，Wine 是唯一的路。

## 原因

Wine 必须在 CoreAudio 之上模拟一整套 Windows 音频栈。它的现代路径（**WASAPI**）采样率转换做得很糟 —— 低音量、爆音、变调都是这么来的。问题出在 Wine 的转换环节，不在 Mac 的音频设备上。

## 修复

Ren'Py 启动时、引擎初始化之前，会读取游戏可执行文件旁边的 `environment.txt`。把这两行放进去：

```
SDL_AUDIODRIVER = "winmm"
RENPY_SOUND_BUFSIZE = "8192"
```

- `winmm` —— 老式、简单的 Windows 音频路径。Wine 对它的模拟远比 WASAPI 好。
- `RENPY_SOUND_BUFSIZE` —— 引擎里未见文档的开关，是从引擎源码里翻出来的；8192 是默认值的 4 倍。缓冲区太小、播放中途耗尽，正是爆音的典型成因。

把本文件旁边的 `environment.txt` 复制到每个安装目录里，和`A_Second_Chance_to_Relive_Summer.exe` 放在同一层：

```
CSE-2.1.0-pc/environment.txt
CSE-1.0-pc/environment.txt
```

然后退出游戏再启动就行 —— 这个文件由游戏自己读取，不需要重启瓶子。Steam 的文件校验和游戏更新都不会动它。

想确认文件确实被读取了：把驱动改成 `dummy` 再启动，游戏应该完全没有声音。确认后改回来。

## 无效的尝试

- 在"音频 MIDI 设置"里更换输出设备或采样率（44.1 / 48 / 96 kHz）。问题在 Wine，不在设备。
- 在 CrossOver 瓶子配置里设音频选项。这些设置需要完整 **退出瓶子（Quit Bottle）** 才生效，所以有几次测试其实压根没真正应用过。`environment.txt` 完全避开了这个坑 —— 这也是优先用它的原因。

如果 `winmm` 在别的环境上失效，下一个可试的是同一个文件里改成 `directsound` 或 `dsound` —— 每次测试只改一行、重启一次游戏。

## 在瓶子外运行 `savefix`

`savefix.py` 通过 `%APPDATA%` 定位实时存档目录，而 macOS 和 Linux 上没有这个变量，所以它会报 `no Ren'Py save folder found in %APPDATA%\RenPy` 退出。把它指向瓶子里的Roaming 目录，就能原生运行 —— 完全不经过 Wine：

```sh
cd "<瓶子>/drive_c/Program Files (x86)/Steam/steamapps/common/CSE-1.0-pc"
APPDATA="<瓶子>/drive_c/users/crossover/AppData/Roaming" \
  uv run --quiet --with ecdsa python tools/savefix.py
```

CrossOver 默认安装下，`<瓶子>` 是 `~/Library/Application Support/CrossOver/Bottles/Steam`。在 Linux/Proton 上用户目录是 `users/steamuser`，不是 `users/crossover`。

上面是只读检查；`fix` 和 `sync` 用同一个变量即可。

## 通用性

这个修复不限于本游戏。任何在 Wine 或 CrossOver 下运行的 Windows Ren'Py 游戏，把同一个 `environment.txt` 放到它的 `.exe` 旁边就行。

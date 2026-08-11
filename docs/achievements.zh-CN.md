# Steam 成就永远不解锁

[English](achievements.md) · **简体中文**

## 症状

你一路玩过多个成就触发点，Steam 上什么都没弹，而且 `log.txt` 里没有任何报错。
游戏本身认为它成功了 —— `game/saves/persistent` 里已经有：

```
_achievements: new_1 … new_8
```

## 原因

游戏代码没问题。`game/scripts.rpa` → `archievement.rpyc` 的注册和授予都是对的：

```python
achievement.register('new_1', steam='achievement_1')   # … 一直到 new_11
achievement.grant('new_1')                             # 从 script_chapter_1/2/3 调用
```

Steam 那一侧是死的，因为这个游戏包里**根本没有 `steam_api64.dll`**。
见 `renpy/common/00steam.rpy:1002`：

```python
dll_path = os.path.join(os.path.dirname(sys.executable), dll_name)  # steam_api64.dll
has_steam = os.path.exists(dll_path)
if not has_steam:
    return            # 静默返回 —— 没有报错，也没有日志
```

`lib/py3-windows-x86_64/` 里只有 `d3dcompiler_47.dll`、`libEGL.dll`、
`libGLESv2.dll`、`libpython3.12.dll`、`librenpython.dll`、`libwinpthread-1.dll`
和 `nvdrs.dll`。全目录树搜索也找不到任何 Steam 二进制文件 —— 只有
`lib/python3.12/steamapi.pyc`，那是 ctypes 封装层，没有 DLL 就毫无用处。

所以 `steam_init()` 提前返回，Steam 后端从未被加入，`achievement.grant()` 就退化到
只写 persistent 的后端。整个过程静默失败，这就是日志里什么都没有的原因。

游戏内也没有成就图鉴（`screens.rpyc` / `newScreens.rpyc` 里没有任何成就字符串），
所以 Steam 本来就是成就唯一可能显示的地方。

## 修复

把 **Steamworks SDK 1.62** 的 `steam_api64.dll` 放到：

```
CSE-2.1.0-pc/lib/py3-windows-x86_64/steam_api64.dll     # 319584 字节
```

和 `librenpython.dll` 同一个文件夹 —— 那正是 `00steam.rpy` 查找的位置
（`os.path.dirname(sys.executable)`）。然后**通过 Steam 启动**游戏；在
macOS/Linux 上还要保证 Steam 客户端运行在同一个 Wine 前缀 / 瓶子里，这样 appid 才
能被传进来。

### 版本必须精确匹配

`steamapi.load()` 会用直接属性访问的方式**一次性绑定全部 1067 个符号**，没有
`getattr` 兜底，也没有异常处理表。只要缺一个导出符号就会抛 `AttributeError`，
`steam_init()` 捕获后禁用 Steam —— 结果就是你现在这种静默无效。Ren'Py 8.5 要的版本
窗口非常窄：

| SDK | 缺失符号数 |
|---|---|
| 1.61 | **14** —— `SteamFriends_v018`、`SteamUGC_v021`、`SteamRemotePlay_v003` 及其方法 |
| 1.62 | **0** ✅ |
| 更新版本（1.6x+） | **59** —— `SteamUtils_v010`、`SteamApps_v008`、`SteamInput_v006`、`SteamGameSearch_v001`、`SteamMusicRemote_v001`…… |

1.61 和更新的 SDK 缺的是**互不重叠**的两组：`Friends_v018` / `UGC_v021` /
`RemotePlay_v003` 比 1.61 新，而 `Utils_v010` / `Apps_v008` / `Input_v006` 比当前
SDK 旧。1.62 是唯一同时满足两端的版本。

复制前先检查候选 DLL —— 六项必须全部命中：

```sh
for s in SteamAPI_SteamUtils_v010 SteamAPI_SteamApps_v008 SteamAPI_SteamInput_v006 \
         SteamAPI_SteamFriends_v018 SteamAPI_SteamUGC_v021 SteamAPI_SteamRemotePlay_v003; do
  printf '%s %s\n' "$(grep -ac "$s" steam_api64.dll)" "$s"
done
```

六个 `1` → DLL 正确。出现任何 `0` → SDK 版本不对，不要用。

### 从哪里获取

- 官方：`partner.steamgames.com/downloads/list` → `steamworks_sdk_162.zip` →
  `sdk/redistributable_bin/win64/steam_api64.dll`。需要 Steamworks 合作伙伴账号。
- 同一批可再分发二进制的公开镜像：`julianxhokaxhiu/SteamworksSDKCI` 的 releases，
  按 SDK 版本打了 tag。

**绝不要**从破解版游戏里拿。Goldberg / SmartSteamEmu / CreamAPI 这类替换件文件名
完全一样，但它们只会在本地伪造成就，不会真正发给 Steam。

## 验证 DLL 是否被加载

`steam_init()` 会记录结果（`00steam.rpy:1059`/`1062`）。检查 `log.txt`：

| 日志行 | 含义 |
|---|---|
| `Initialized steam.` | DLL 已加载，1067 个符号全部绑定成功，`SteamAPI_InitFlat` 返回 0 ✅ |
| `Failed to initialize steam: <error>` | DLL 找到了，但别的环节出错 |
| *两行都没有* | 仍然没找到 DLL —— 还在走旧的静默路径 |

本机安装上已确认成功：

```
Initialized steam.
 - Init at renpy/common/00steam.rpy:879 took 1044 ms.
```

那 1044 毫秒就是真实的 Steam 握手耗时。

## 补发已经拿到的成就

`achievement.sync()`（`00achievement.rpy:292`）会把 `persistent` 里的全部内容推上去：

```python
for a in persistent._achievements:
    for i in backends:
        if not i.has(a):
            i.grant(a)
```

**关键陷阱：** 在 `archievement.rpy` 里，那些 `register()` 调用**和**两处 `sync()`
全都写在 `label achievement(who):` 内部，没有 `init python` 块。所以启动时什么都不
会执行，Steam 名称映射（`new_1` → `achievement_1`）在该 label 被调用之前一直是空的。

因此：读取存档，**继续玩到下一个成就触发点**。到达任意一个触发点都会执行末尾那个
`sync()`，它会遍历 `persistent._achievements` 的**全部**条目 —— 不只是你刚触发的那
一个 —— 把它们一起推上去。预计会连续弹出八到九个成就。

只有已经写进 `persistent` 的才会被推送；还没拿到的仍然要正常去解锁。

> label **开头**那个 `sync()` 是游戏脚本自身的 bug：第一次调用时名称映射还是空的，
> 于是它推的是原始的 `new_1` 而不是 `achievement_1`，Steam 会直接丢弃。无害 ——
> 末尾那个 `sync()` 会把事情做对。

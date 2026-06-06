# Win7 打包说明

## 结论

当前项目如果要在 Windows 7 离线运行，最简单的方案是：

1. 用 `Python 3.8 x64` 打包
2. 用 `PyInstaller 5.13.2` 打包
3. 不要用 `Python 3.14` 打包给 Win7

## 一次性准备

在打包机器上安装：

- `Python 3.8 x64`
- `PyInstaller 5.13.2`

安装命令：

```powershell
py -3.8 -m pip install pyinstaller==5.13.2
```

## 打包命令

项目目录下执行：

```powershell
.\build.ps1
```

脚本会优先使用：

```powershell
py -3.8
```

如果没有找到 `Python 3.8`，脚本会直接报错提醒，不会再错误地用 `Python 3.14` 打包。

## 运行方式

把生成的文件复制到 Win7：

```text
dist\TrainDataManager.exe
```

这是离线运行方式，不依赖联网。

## 如果还报缺少 DLL

优先检查 Win7 是否为：

- `Windows 7 SP1`
- `64 位系统`

如果不是 SP1，先升级到 `Win7 SP1`。

如果仍有运行库问题，再补装：

- `Microsoft Visual C++ Redistributable 2015-2022 x64`

但第一优先级仍然是：`必须改用 Python 3.8 重新打包`。

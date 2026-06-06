# 列车数据管理

## 功能
- 导入 JSON 到本地 SQLite 数据库
- 按 JSON 顶层键自动建表
- 每次重新导入前覆盖全部旧表
- 顶部显示 `车次._key.version.最新版本号`
- 按 `车次._key` 实时模糊查询
- 左侧显示匹配结果，点击 `_key` 后中间竖排展示详情
- 右侧联动查询 `表示器显示._key`

## 运行并自动打包
```powershell
.\run.ps1
```

关闭程序窗口后，会自动重新打包生成最新 `dist\TrainDataManager.exe`。

## 仅运行
```powershell
python app.py
```

## 打包 exe
```powershell
.\build.ps1
```

生成文件在 `dist\TrainDataManager.exe`

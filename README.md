<img width="940" height="760" alt="image" src="https://github.com/user-attachments/assets/80344486-ffc3-4522-9af5-adf87200846b" /># SF HTML 图片上传转换工具

一个面向 Windows 的本地小工具，用于把 Word/网页导出的 `.htm/.html` 文件中的本地图片批量上传到 SF 系统，并把 `<img src="">` 自动替换为 SF 返回的图片 URL。

转换后会生成可直接复制到 SF 富文本编辑器源码模式的 `.txt` 文件。

![工具截图](<img width="940" height="760" alt="image" src="https://github.com/user-attachments/assets/4365890a-0c27-4957-9add-11cc9541a36c" />
)

## 功能

- 支持添加单个或多个 `.htm/.html` 文件
- 支持选择 HTML 文件夹，自动递归识别其中的 HTML 文件
- 支持拖拽 HTML 文件或文件夹到窗口
- 自动去重，避免重复处理同一文件
- 自动识别同名 `.files` 图片目录
- 支持粘贴 SF 上传 `token`，也兼容完整 Request URL
- 默认清洗 Word 导出的冗余 HTML 样式
- 支持预演检查，不上传也能验证图片路径
- 输出 `.txt`，方便直接全选复制
- 输出冲突时自动追加 `_2`、`_3`，不覆盖旧文件

## 下载

Windows 10 / Windows 11 64 位可直接下载：

[下载 Windows 版压缩包](downloads/SF_HTML转换工具_Windows版.zip)

压缩包内包含：

- `SF_HTML转换工具.exe`
- `使用说明.md`

## 使用方法

1. 双击运行 `SF_HTML转换工具.exe`。
2. 粘贴 SF 上传 `token`。
3. 点击“添加HTML文件”或“选择HTML文件夹”，也可以直接拖拽文件/文件夹。
4. 图片文件夹建议留空，程序会优先自动识别同名 `.files` 文件夹。
5. 先点“预演检查（不上传）”。
6. 确认无误后点“开始正式转换”。
7. 打开生成的 `.txt`，复制全部内容到 SF 富文本编辑器源码模式。

输出结构：

```text
原 HTML 所在目录/
  已转换/
    已转换_原文件名.txt
    转换日志/
      已转换_原文件名_日志.txt
```

## token 说明

窗口中推荐只粘贴 token 本身。

如果误粘完整 Request URL，也可以兼容：

```text
https://serviceforce.lenovo.com.cn/api/wb/upload/file?token=xxxx
```

## 从源码运行

```powershell
pip install -r requirements-dev.txt
python src/sf_import_gui.py
```

## 打包 EXE

```powershell
pyinstaller --noconfirm --clean --onefile --windowed --name "SF_HTML转换工具" --icon "assets/sf_html_tool.ico" --add-data "assets/sf_html_tool.ico;." --collect-all tkinterdnd2 src/sf_import_gui.py
```

打包结果位于：

```text
dist/SF_HTML转换工具.exe
```


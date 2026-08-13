# VideoMind Agent 参赛产品说明

本目录包含一套 15 页、16:9、简体中文的可编辑参赛演示文稿。正文、标题、流程图、架构框、箭头、标签、页码和截图占位框均为 PowerPoint 原生对象。

## 文件

- `VideoMind-Agent-参赛产品说明.pptx`：正式可编辑演示文稿。
- `VideoMind-Agent-参赛产品说明.pdf`：通过 Microsoft PowerPoint 导出的提交预览版。
- `validation-report.json`：PPTX 结构自动检查结果。
- `../../scripts/generate_competition_ppt.py`：使用 python-pptx 构建并验证全部原生对象。
- `../../scripts/generate_competition_ppt.ps1`：仅将已验证 PPTX 导出为 PDF，不参与页面构建。

## 如何修改 PPT

使用 Microsoft PowerPoint 或 WPS 打开 PPTX。所有文字、颜色、字号、位置、矩形和箭头均可直接选择和修改。建议保留 16:9 页面比例与微软雅黑字体。

## 如何替换产品截图

第 8、9、11、12 页包含浅绿色虚线截图占位框。选中并删除占位框及说明文字，然后使用“插入 → 图片”放入真实产品截图，使用“裁剪”调整画面比例。

比赛提交前建议替换：

- 第 8 页：SubtitleEditor 实际截图。
- 第 9 页：播放器与 SubtitleEditor 同步截图。
- 第 11 页：双语字幕播放器截图。
- 第 12 页：Summary 和 Q&A 实际截图。

## 修改团队和链接

第 1 页和第 15 页底部预留了参赛成员、学校、专业、Demo、GitHub、团队和联系方式字段，直接点击文本框替换即可。

## 重新生成

需要 Python 与 `python-pptx`。如需脚本自动导出 PDF，还需要 Windows 与 Microsoft PowerPoint。在项目根目录执行：

```powershell
python scripts/generate_competition_ppt.py
```

如只需把已经生成的 PPTX 重新导出为 PDF，可直接执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/generate_competition_ppt.ps1 `
  -PptxPath "docs/competition/VideoMind-Agent-参赛产品说明.pptx" `
  -PdfPath "docs/competition/VideoMind-Agent-参赛产品说明.pdf"
```

重新生成会覆盖本目录中同名 PPTX 和 PDF；如果已经手工修改 PPT，请先另存备份。

## 导出 PDF

Python 会先独立生成并重新打开验证 PPTX。验证通过后，脚本才调用本机 Microsoft PowerPoint 执行 `Open + ExportAsFixedFormat`；COM 不修改任何页面对象。也可以在 PowerPoint/WPS 中手工使用“文件 → 导出/另存为 → PDF”。

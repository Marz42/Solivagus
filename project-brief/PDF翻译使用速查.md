# PaddleOCR-VL PDF 翻译 CLI 速查表

Get-ChildItem -LiteralPath "D:\PDFS" -Filter "*.pdf" -File | ForEach-Object { Write-Host "`n========== 正在处理：$($_.Name) =========="; & python "D:\Repos\PDF2MD\pdf_translate_cli.py" $_.FullName --env-file "D:\Repos\PDF2MD\.env"; if ($LASTEXITCODE -ne 0) { Write-Warning "处理失败：$($_.FullName)" } }

## 1. 基本配置

脚本依赖当前目录中的 `.env`：

```dotenv
LLM_API_BASE=https://api.example.com/v1
LLM_API_KEY=你的API密钥
LLM_MODEL=你的模型名称
```

检查脚本参数：

```powershell
python pdf_translate_cli.py --help
```

---

## 2. 标准使用流程

### 第一次只测试 OCR

```powershell
python pdf_translate_cli.py "D:\Documents\paper.pdf" --ocr-only
```

默认输出目录：

```text
D:\Documents\paper.translation\
```

主要检查：

```text
source.md
assets\
parsed\
state.json
```

### 开始翻译或继续翻译

```powershell
python pdf_translate_cli.py "D:\Documents\paper.pdf"
```

脚本会自动：

* 复用已有 OCR 结果；
* 跳过已经完成的翻译块；
* 从未完成的翻译块继续；
* 更新最终中文和双语 Markdown。

最终输出：

```text
translated.zh.md
translated.bilingual.md
```

---

## 3. 中断与续跑

翻译过程中可以按：

```text
Ctrl+C
```

重新执行原命令即可继续：

```powershell
python pdf_translate_cli.py "D:\Documents\paper.pdf"
```

不要添加 `--force-ocr` 或 `--force-translate`，否则会主动清除对应缓存。

---

## 4. 常用命令

### 仅生成中文版

```powershell
python pdf_translate_cli.py "paper.pdf" --zh-only
```

### 指定 GPU

```powershell
python pdf_translate_cli.py "paper.pdf" --device "gpu:0"
```

### 指定 CPU

```powershell
python pdf_translate_cli.py "paper.pdf" --device "cpu"
```

### 处理旋转或方向异常的扫描件

```powershell
python pdf_translate_cli.py "scan.pdf" --use-orientation
```

### 处理拍照、弯曲或透视变形的文档

```powershell
python pdf_translate_cli.py "scan.pdf" --use-orientation --use-unwarping
```

### 开启图表识别

```powershell
python pdf_translate_cli.py "report.pdf" --use-chart-recognition
```

普通论文建议先不开启，默认保留图表原图即可。

### 使用术语表

```powershell
python pdf_translate_cli.py "paper.pdf" --glossary "glossary.yaml"
```

术语表可以简单写成：

```yaml
retrieval-augmented generation: 检索增强生成
context window: 上下文窗口
fine-tuning: 微调
inference: 推理
embedding: 嵌入
```

### 缩小翻译分块

适用于上下文窗口较小，或者容易超时的模型：

```powershell
python pdf_translate_cli.py "paper.pdf" --chunk-chars 8000
```

默认值：

```text
12000 字符
```

### 增加 API 超时时间

```powershell
python pdf_translate_cli.py "paper.pdf" --timeout 600
```

默认单次请求超时为 300 秒。

### 增加失败重试次数

```powershell
python pdf_translate_cli.py "paper.pdf" --retries 5
```

默认最多尝试 3 次。

### API 不支持 temperature

```powershell
python pdf_translate_cli.py "paper.pdf" --no-temperature
```

---

## 5. 强制重新处理

### 重新 OCR

```powershell
python pdf_translate_cli.py "paper.pdf" --force-ocr
```

这会忽略已有 OCR 缓存，重新解析整个 PDF。

### 重新翻译全部内容

```powershell
python pdf_translate_cli.py "paper.pdf" --force-translate
```

这会保留 OCR 结果，但重新调用 API 翻译所有块。

### OCR 和翻译全部重做

```powershell
python pdf_translate_cli.py "paper.pdf" --force-ocr --force-translate
```

---

## 6. 指定配置文件

当 `.env` 不在当前 PowerShell 目录时：

```powershell
python pdf_translate_cli.py "paper.pdf" `
  --env-file "D:\PDFTranslator\.env"
```

批量处理时建议始终指定 `.env` 的绝对路径。

---

## 7. 指定其他翻译模型

```powershell
python pdf_translate_cli.py "paper.pdf" `
  --api-base "https://api.example.com/v1" `
  --api-key "YOUR_API_KEY" `
  --model "MODEL_NAME"
```

更推荐把密钥写入 `.env`，命令行只覆盖模型：

```powershell
python pdf_translate_cli.py "paper.pdf" --model "MODEL_NAME"
```

---

## 8. 输出目录结构

```text
paper.translation\
├── source.md
├── translated.zh.md
├── translated.bilingual.md
├── state.json
├── assets\
├── parsed\
└── chunks\
    ├── b00001.source.md
    ├── b00001.zh.md
    ├── b00002.source.md
    └── b00002.zh.md
```

各文件用途：

* `source.md`：PaddleOCR-VL 解析后的原文。
* `translated.zh.md`：完整中文版。
* `translated.bilingual.md`：英中对照版。
* `state.json`：OCR 与翻译进度状态。
* `assets\`：提取的图片。
* `chunks\`：分块原文和译文，可用于排查失败块。
* `parsed\`：PaddleOCR 原始解析结果。

---

## 9. 常见问题

### 再次执行会不会重新 OCR？

正常不会。只要输出目录和状态文件仍在，脚本会复用已有结果。

### 中断后会不会重新翻译已完成内容？

正常不会。脚本会读取已有块和状态，从未完成部分继续。

### 修改术语表后会发生什么？

翻译配置发生变化时，相关翻译缓存可能失效并重新生成，但 OCR 结果仍可复用。

### 可以移动原始 PDF 吗？

不建议在任务未完成时移动或重命名。默认工作目录与 PDF 文件名和位置相关。

### 可以删除 `chunks` 吗？

任务完成后可以归档或删除，但保留它有利于重新汇总和排查翻译错误。

### 哪个结果最适合日常阅读？

优先使用：

```text
translated.zh.md
```

需要核查译文时使用：

```text
translated.bilingual.md
```

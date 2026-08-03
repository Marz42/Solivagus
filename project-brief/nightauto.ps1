Get-ChildItem `
  -LiteralPath "D:\PDFS" `
  -Filter "*.pdf" `
  -File |
ForEach-Object {
    Write-Host "`n========== 正在处理：$($_.Name) =========="

    & python `
      "D:\Repos\PDF2MD\pdf_translate_cli_v0_2.py" `
      $_.FullName `
      --env-file "D:\Repos\PDF2MD\.env" `
      --chunk-chars 4000 `
      --prevent-sleep

    if ($LASTEXITCODE -ne 0) {
        Write-Warning "文件级任务失败：$($_.FullName)"
    }
}
param(
  [Parameter(Mandatory=$true)][string]$PptxPath,
  [Parameter(Mandatory=$true)][string]$PdfPath
)

# This script only exports an already-generated and validated PPTX to PDF.
# It never creates or edits slides, shapes, text, colors, or layout.
$ErrorActionPreference = "Stop"
$ppt = $null
$pres = $null
try {
  $ppt = New-Object -ComObject PowerPoint.Application
  $pres = $ppt.Presentations.Open($PptxPath, $true, $false, $false)
  # ppSaveAsPDF = 32. SaveAs avoids PowerShell 5 COM overload binding issues.
  $pres.SaveAs($PdfPath, 32)
} finally {
  if ($pres) { $pres.Close() }
  if ($ppt) { $ppt.Quit() }
  if ($pres) { [Runtime.InteropServices.Marshal]::ReleaseComObject($pres) | Out-Null }
  if ($ppt) { [Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null }
}

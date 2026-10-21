# 文件功能：通过 Windows 离线中文语音生成 WP01 自有文案旁白，不调用网络服务或改变系统音频设置。
param([Parameter(Mandatory = $true)][string]$Output, [Parameter(Mandatory = $true)][string]$Text)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$wp01Speech = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $wp01Speech.SelectVoice('Microsoft Huihui Desktop')
    $wp01Speech.Rate = 3
    $wp01Format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(48000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
    $wp01Speech.SetOutputToWaveFile($Output, $wp01Format)
    $wp01Speech.Speak($Text)
} finally {
    $wp01Speech.Dispose()
}

$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType=WindowsRuntime]
$request = [Console]::In.ReadToEnd() | ConvertFrom-Json
$voices = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices
if ($request.operation -eq 'voices') {
    $items = @($voices | ForEach-Object { @{id=$_.Id; name=$_.DisplayName; lang=$_.Language} })
    @{voices=$items} | ConvertTo-Json -Depth 4 -Compress
    exit
}
if ($request.operation -ne 'synthesize') { throw 'Unknown speech operation.' }
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
$stream = $null; $reader = $null; $buffer = $null
try {
    $chosen = $null
    if ($request.voice) {
        $chosen = $voices | Where-Object { $_.Id -eq $request.voice -or $_.DisplayName -eq $request.voice -or ([string]$request.voice).StartsWith($_.DisplayName, [StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1
    }
    if (-not $chosen -and $request.lang) {
        $chosen = $voices | Where-Object { $_.Language -eq $request.lang } | Select-Object -First 1
    }
    if ($chosen) { $synth.Voice = $chosen }
    if ($request.lang -eq 'hi-IN' -and $synth.Voice.Language -ne 'hi-IN') { throw 'No Hindi Windows voice is installed.' }
    $synth.Options.SpeakingRate = [double]$request.rate
    $asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
    $operation = $synth.SynthesizeTextToStreamAsync([string]$request.text)
    $task = $asTask.MakeGenericMethod([Windows.Media.SpeechSynthesis.SpeechSynthesisStream]).Invoke($null, @($operation))
    $stream = $task.GetAwaiter().GetResult()
    $reader = [System.IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($stream)
    $buffer = New-Object System.IO.MemoryStream
    $reader.CopyTo($buffer)
    @{audio=[Convert]::ToBase64String($buffer.ToArray()); voice=$synth.Voice.DisplayName; lang=$synth.Voice.Language} | ConvertTo-Json -Compress
} finally {
    if ($buffer) { $buffer.Dispose() }
    if ($reader) { $reader.Dispose() }
    if ($stream) { $stream.Dispose() }
    $synth.Dispose()
}

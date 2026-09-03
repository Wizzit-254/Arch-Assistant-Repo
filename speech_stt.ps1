param([int]$Duration = 8)
# SAPI dictation helper for Arch voice input.
# Emits one "TEXT:" line per recognized phrase, then exits.
# Uses the blocking Recognize(TimeSpan) loop - avoids PowerShell event binding quirks.
Add-Type -AssemblyName System.Speech
$engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine
$engine.SetInputToDefaultAudioDevice()
$grammar = New-Object System.Speech.Recognition.DictationGrammar
try {
    $engine.LoadGrammar($grammar)
} catch {
    [Console]::Error.WriteLine("ERR:dictation unavailable: $($_.Exception.Message)")
    $engine.Dispose()
    exit 1
}
$elapsed = 0
while ($elapsed -lt $Duration) {
    $span = [math]::Min(4, $Duration - $elapsed)
    try {
        $result = $engine.Recognize([TimeSpan]::FromSeconds($span))
        if ($result -and $result.Text) {
            [Console]::Out.WriteLine("TEXT:" + $result.Text)
        }
    } catch {}
    $elapsed += $span
}
$engine.Dispose()
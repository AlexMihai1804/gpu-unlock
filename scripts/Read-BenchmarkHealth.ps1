param([Parameter(Mandatory=$true)][string]$SinceUtc)
$ErrorActionPreference='Stop'
$since=[DateTimeOffset]::Parse($SinceUtc).LocalDateTime
try {
    $events=@(Get-WinEvent -FilterHashtable @{LogName='System';ProviderName=@('Display','nvlddmkm','Microsoft-Windows-WHEA-Logger');StartTime=$since;Level=1,2,3} -ErrorAction Stop)
} catch {
    if ($_.FullyQualifiedErrorId -like 'NoMatchingEventsFound*') { $events=@() } else { throw }
}
try {
    $sleepEvents=@(Get-WinEvent -FilterHashtable @{LogName='System';ProviderName='Microsoft-Windows-Kernel-Power';StartTime=$since;Id=42,506} -ErrorAction Stop)
    $events+= $sleepEvents
} catch {
    if ($_.FullyQualifiedErrorId -notlike 'NoMatchingEventsFound*') { throw }
}
$details=@(foreach ($event in $events) {
    [xml]$xml=$event.ToXml()
    $fields=[ordered]@{}
    foreach ($item in $xml.SelectNodes("/*[local-name()='Event']/*[local-name()='EventData']/*[local-name()='Data']")) { $fields[$item.GetAttribute('Name')]=$item.InnerText }
    [ordered]@{utc=$event.TimeCreated.ToUniversalTime().ToString('o');id=$event.Id;provider=$event.ProviderName;record_id=$event.RecordId;fields=$fields}
})
[ordered]@{utc=(Get-Date).ToUniversalTime().ToString('o');events=$details} | ConvertTo-Json -Depth 8 -Compress

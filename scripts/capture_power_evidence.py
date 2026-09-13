"""Read Windows power events; overlaps are not lost-CPU-time measurements."""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

command = """
$ErrorActionPreference = 'Stop'
Get-WinEvent -FilterHashtable @{LogName='System';
ProviderName='Microsoft-Windows-Kernel-Power';
StartTime=[datetime]'2026-09-06T00:00:00'; Id=506,507} |
Sort-Object TimeCreated | ForEach-Object {
 [pscustomobject]@{utc=$_.TimeCreated.ToUniversalTime().ToString('o');
 id=$_.Id; record_id=$_.RecordId}
} | ConvertTo-Json
"""


def main():
    completed = subprocess.run(["pwsh", "-NoProfile", "-Command", command],
                               capture_output=True, text=True, check=True)
    events = json.loads(completed.stdout)
    intervals, unmatched = [], []
    start = None
    for event in events:
        if event["id"] == 506:
            if start is not None:
                unmatched.append(start)
            start = event
        elif start is not None:
            intervals.append([start, event])
            start = None
        else:
            unmatched.append(event)
    if start is not None:
        unmatched.append(start)
    windows = {
        "old": ("2026-09-07T01:04:25.312917+00:00", "2026-09-07T05:16:19.490939+00:00"),
        "new": ("2026-09-09T17:10:27.462148+00:00", "2026-09-11T10:51:12.242619+00:00"),
    }
    overlaps = {}
    for name, bounds in windows.items():
        left, right = map(datetime.fromisoformat, bounds)
        selected = []
        for entry, exit_event in intervals:
            begin = datetime.fromisoformat(entry["utc"])
            end = datetime.fromisoformat(exit_event["utc"])
            seconds = max(0, (min(end, right) - max(begin, left)).total_seconds())
            if seconds:
                selected.append(dict(entry=entry, exit=exit_event, overlap_seconds=seconds))
        overlaps[name] = dict(intervals=selected,
                              total_overlap_seconds=sum(x["overlap_seconds"] for x in selected))
    result = dict(events=events, unmatched=unmatched, run_windows=windows, overlaps=overlaps,
                  scope="Modern Standby event overlap, NOT measured process suspension time")
    sleep_command = """
$ErrorActionPreference = 'Stop'
Get-WinEvent -FilterHashtable @{LogName='System';
ProviderName='Microsoft-Windows-Power-Troubleshooter';
StartTime=[datetime]'2026-09-06T00:00:00'; Id=1} | ForEach-Object {
 $fields = @{}
 ([xml]$_.ToXml()).Event.EventData.Data | ForEach-Object { $fields[$_.Name] = $_.'#text' }
 [pscustomobject]@{record_id=$_.RecordId; sleep=$fields['SleepTime'];
 wake=$fields['WakeTime']; effective_state=$fields['EffectiveState']}
} | ConvertTo-Json
"""
    sleeps = json.loads(subprocess.check_output(
        ["pwsh", "-NoProfile", "-Command", sleep_command], text=True))
    result["sleep_wake_events"] = sleeps
    result["sleep_wake_overlap"] = {}
    for name, bounds in windows.items():
        left, right = map(datetime.fromisoformat, bounds)
        selected = []
        for event in sleeps:
            begin = datetime.fromisoformat(event["sleep"])
            end = datetime.fromisoformat(event["wake"])
            seconds = max(0, (min(end, right) - max(begin, left)).total_seconds())
            if seconds:
                selected.append(dict(**event, overlap_seconds=seconds))
        result["sleep_wake_overlap"][name] = selected
    with Path(sys.argv[1]).open("x", encoding="utf-8", newline="\n") as out:
        json.dump(result, out, indent=2)
        out.write("\n")
    print(json.dumps({k: v["total_overlap_seconds"] for k, v in overlaps.items()}))
    print(json.dumps({k: sum(x["overlap_seconds"] for x in v)
                      for k, v in result["sleep_wake_overlap"].items()}))


if __name__ == "__main__":
    main()

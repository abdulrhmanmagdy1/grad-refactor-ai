"""Report hardware without sending it anywhere or reading credentials."""

import json
import platform
import shutil
import subprocess
import sys

info = {
    "python": sys.version.split()[0],
    "os": platform.system(),
    "architecture": platform.machine(),
    "gpu": "not detected; confirm manually",
}
if shutil.which("nvidia-smi"):
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode == 0:
        info["gpu"] = result.stdout.strip()
print(json.dumps(info, ensure_ascii=False, indent=2))

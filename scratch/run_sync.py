import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

print("Running importar_excel_dto_2016.py synchronously...")
process = subprocess.Popen(
    [str(ROOT / ".venv" / "Scripts" / "python.exe"), "importar_excel_dto_2016.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    cwd=str(ROOT),
    bufsize=1  # line buffered
)

for line in process.stdout:
    print(line, end="")
    sys.stdout.flush()

process.wait()
print(f"\nFinished with exit code: {process.returncode}")

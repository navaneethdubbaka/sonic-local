# Phase 0

Prove routing on text before mouse or mic.

```powershell
cd e:\Sonic-local
.\venv\Scripts\python.exe -m pip install -e ".[dev]"
copy .env.example .env
# optional: set SONIC_CLOUD_API_KEY in .env for the cloud smoke test
```

Route one utterance:

```powershell
.\venv\Scripts\python.exe -m sonic.cli route "Open Notepad" --no-cloud
.\venv\Scripts\python.exe -m sonic.cli route "What's 15% of 80"
.\venv\Scripts\python.exe -m sonic.cli route "Explain LangGraph" --graph
```

Force CPU:

```powershell
$env:SONIC_DEVICE="cpu"
.\venv\Scripts\python.exe -m sonic.cli route "Open Notepad" --no-cloud
```

Eval the labeled set (downloads Laya typed-decisions on first run):

```powershell
.\venv\Scripts\python.exe -m sonic.cli eval
```

Exit bar: accuracy ≥ 85%, refuse violations = 0. Results land in `eval_results/phase0_routes.json` and `docs/phase0_calibration.md`.

Optional Needle dry-run:

```powershell
.\venv\Scripts\python.exe -m pip install -e ".[needle]"
.\venv\Scripts\python.exe -m sonic.cli route "Open Notepad" --no-cloud
```

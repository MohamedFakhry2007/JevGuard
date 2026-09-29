# Run the JevGuard demo on your own computer

You need Python 3.10 or newer and Git. No API key is needed: the demo replays real Jev answers that are saved in the repo.

## Windows (PowerShell)
```powershell
git clone --branch claude/magical-faraday-7rml4l https://github.com/MohamedFakhry2007/JevGuard.git
cd JevGuard
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[ui]"
streamlit run app/streamlit_app.py
```
If PowerShell blocks the activate script, run `Set-ExecutionPolicy -Scope Process Bypass` first, or use `.venv\Scripts\activate.bat` in Command Prompt.

## macOS or Linux
```bash
git clone --branch claude/magical-faraday-7rml4l https://github.com/MohamedFakhry2007/JevGuard.git
cd JevGuard
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[ui]"
streamlit run app/streamlit_app.py
```

Streamlit opens http://localhost:8501 in your browser.

## What you will see
- **Recorded real Jev answers** (default): pick one of the saved tune-half examples. Edited text has no recording, and the app says so.
- **Simulated (NOT Jev)**: a keyword stand-in so you can try your own text. Always stamped with a warning.
- **Live Jev**: appears only if the environment variable `TYPESAFE_API_KEY` is set on your machine.

## Check that everything works
```bash
pip install -e ".[dev]"
pytest -q
```
Install with `-e` (editable). The app finds its data files relative to the source folder.

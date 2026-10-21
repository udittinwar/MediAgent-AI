# MediAgent AI — supplied UI version

`app_groq.py` is copied from the code file provided in chat without changing
its application code.

## Run on Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements_groq.txt
$env:LLM_PROVIDER="groq"
$env:GROQ_API_KEY="YOUR_REAL_GROQ_API_KEY"
$env:GROQ_MODEL="openai/gpt-oss-20b"
.\.venv\Scripts\python.exe -m streamlit run app_groq.py
```

The app code references optional image assets named `topdocs_logo`, `doctor_1`,
`doctor_2`, and `doctor_3` inside an `assets` folder (or beside the script).
Those image files were not included in the provided text file. If they are
absent, the code falls back to its built-in placeholder image.

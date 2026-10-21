
# MediAgent AI — Multi-Agent Healthcare Assistant

Submission-ready academic implementation built around:

- Streamlit UI
- Supervisor / Orchestrator Agent
- 10 specialist task agents
- Clinical Safety Reviewer
- Ollama local LLM (`llama3.2:1b` by default)
- SQLite persistence
- Automatic navigation after Supervisor handoff
- Doctor finder
- Appointment book / reschedule / cancel
- Medical report TXT/PDF summarization
- Medication information
- Symptom triage
- Patient education
- Support ticketing
- Follow-up guidance

## 10 task agents

1. Emergency Triage Agent
2. Patient Assistant Agent
3. Symptom Triage Agent
4. Doctor Recommendation Agent
5. Appointment Agent
6. Medical Report Analysis Agent
7. Medication Safety Information Agent
8. Patient Education Agent
9. Customer Support Agent
10. Follow-up & Care Guidance Agent

Cross-cutting components:

- Supervisor / Orchestrator Agent
- Clinical Safety Reviewer Agent

## Windows setup

Open PowerShell in the project folder:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Make sure Ollama is installed and the model exists:

```powershell
ollama list
```

Run the model:

```powershell
ollama run llama3.2:1b
```

In another terminal, start Streamlit:

```powershell
.\venv\Scripts\python.exe -m streamlit run app.py
```

## Environment variables (optional)

PowerShell:

```powershell
$env:OLLAMA_MODEL="llama3.2:1b"
$env:OLLAMA_BASE_URL="http://localhost:11434"
```

Default values are already configured, so no `.env` file is required.

## Database

The app creates `healthcare.db` automatically and enables SQLite WAL mode.

Tables:

- appointments
- tickets
- reports
- interactions

## Architecture for viva/demo

User
→ Streamlit UI
→ Supervisor / Orchestrator
→ Specialist Agent
→ Clinical Safety Reviewer
→ Response / Workflow
→ SQLite persistence

Example:

`"I need a cardiologist"`

→ Supervisor detects doctor intent
→ Doctor Recommendation Agent
→ Cardiology matches are returned
→ User is automatically routed to **Find a Doctor**

Example:

`"I want to book an appointment"`

→ Supervisor
→ Appointment Agent
→ **Appointments** page opens automatically

Example:

`"Explain my blood report"`

→ Supervisor
→ Report Analysis Agent
→ **Medical Reports** page opens automatically

## Important

This is an academic/demo system. Replace demo doctor records, routing rules,
and local-only inference with approved production services, authentication,
authorization, audit controls, privacy controls, clinical validation, and
deployment infrastructure before real clinical use.

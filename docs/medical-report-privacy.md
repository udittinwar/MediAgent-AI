# Medical Report Analysis — Data Flow and Privacy

## 1. Purpose and scope

This document describes the medical-report handling implemented in the current MediAgent-AI academic demonstration. It is based on the application code and should be updated when the data flow or deployment configuration changes.

The application is a demonstration, not a production-ready clinical data management system.

## 2. Report input

The application accepts report text pasted by the user or extracted from TXT and PDF uploads.

- The application limits the report text submitted for analysis to 12,000 characters.
- For longer reports, only the first 12,000 characters are analyzed.
- The application sends the report text to the configured language-model provider for summarization.
- The character limit is an input-size safeguard, not a privacy or security guarantee.

## 3. Language-model provider

The application defaults to Groq unless the `LLM_PROVIDER` environment variable selects another supported provider.

### Groq

When Groq is configured and used, report content included in the model request is transmitted to an external cloud service for processing.

Before using real or identifiable medical information, review the provider's current privacy policy, data-retention terms, applicable contractual terms, and organizational requirements. Do not assume that the application controls the provider's retention or processing practices.

### Ollama

Ollama is an alternative provider. Processing may remain on the local machine when the application is configured to use a local Ollama instance.

Verify the configured endpoint and actual deployment. A remote Ollama endpoint would not provide the same local-processing assumption.

## 4. Local report database

The report database schema includes `title`, `report_text`, `summary`, and `created_at`.

In the current report-saving code:

- The title is stored, limited to 200 characters.
- The `report_text` field receives the literal placeholder `[NOT STORED]`, rather than the original report text.
- The generated summary is stored, limited to 15,000 characters.
- A creation timestamp is stored.

Therefore, the database does not store the original report text in this report record through the shown insert operation. However, the generated summary may still contain sensitive or identifying information.

This behavior does not prove that report content is absent from every other location, such as application memory, session state, provider-side systems, uploaded-file handling, backups, or other logs. Those paths must be reviewed separately.

## 5. Safety and privacy limitations

- The application sends report content to the configured model provider for analysis.
- Avoid using real patient information unless the deployment has been reviewed and approved for that use.
- Do not treat a placeholder in one database column as proof of complete data deletion or end-to-end privacy.
- Review access controls, secrets management, database access, session handling, logging, backups, and file-upload behavior before deployment.
- Review provider policies and the actual endpoint configuration before claiming that processing is private or local.
- Do not claim regulatory compliance or guaranteed confidentiality without a proper technical and legal assessment.

## 6. Recommended safeguards

1. Use synthetic or de-identified reports during development and demonstrations.
2. Keep API keys in environment variables and out of source control.
3. Verify the LLM provider and endpoint before processing sensitive information.
4. Limit access to stored summaries and report history.
5. Check whether uploaded files, temporary data, logs, or session state retain sensitive content.
6. Establish retention and deletion procedures for stored summaries and other application data.
7. Reassess privacy whenever providers, prompts, logging, or deployment settings change.

## 7. Current implementation status

The inspected code caps report input at 12,000 characters and stores `[NOT STORED]` in the report database's raw-text field while saving the generated summary.

The code inspected does not, by itself, establish provider-side retention behavior or prove that no copy of report content exists elsewhere. Those claims require separate configuration and deployment review.

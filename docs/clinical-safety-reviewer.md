# Clinical Safety Reviewer — Implementation and Limitations

## 1. Purpose

The `ClinicalSafetyReviewerAgent` is a rule-based safety filter in the MediAgent-AI academic project. It checks generated response text for selected patterns associated with potentially unsafe medical advice.

It is a basic safeguard, not a clinically validated medical safety system.

## 2. Current implementation

The reviewer defines six regular-expression checks in `BAD_PATTERNS`:

| Category | Example pattern or wording detected |
|---|---|
| Guaranteed outcomes | "guarantee" or "guaranteed" |
| Definitive diagnosis | "you definitely have", "you certainly have", or "diagnosis is" |
| Specific dosage | "take" followed by a numeric amount and a supported unit: mg, ml, mcg, or g |
| Medication discontinuation | "stop taking" |
| Unsafe dose escalation | "double your dose" |

The patterns are case-insensitive.

## 3. Review and sanitization flow

1. `review(text)` checks the response against each configured pattern.
2. If one or more patterns match, it returns `NEEDS_REVISION` and the corresponding issue labels.
3. If no patterns match, it returns `PASS`.
4. `sanitize(text)` replaces a flagged response with a standard safety message advising consultation with a qualified healthcare professional and directing users to emergency services when appropriate.
5. The orchestrator applies this sanitization before returning an agent result and can attach safety status and issue metadata.

A `PASS` result means only that none of the configured patterns matched. It does not mean the response has been medically verified.

## 4. Known limitations

### Pattern coverage

The reviewer checks a small, fixed set of phrases. It can miss unsafe instructions expressed using different wording, synonyms, indirect language, or other languages.

### Context awareness

The reviewer does not interpret the clinical context of a sentence. A phrase may be flagged even when it appears in a warning, quotation, educational explanation, or negated statement.

### Medical accuracy

The reviewer does not independently verify diagnoses, medication facts, contraindications, drug interactions, treatment recommendations, or report interpretations.

### Dosage coverage

The current dosage pattern covers only certain units and a specific sentence structure. Other units, formats, and equivalent instructions may not match.

### No clinical validation

The reviewer does not use a validated medical knowledge base, clinical guidelines, a clinician approval workflow, or a comprehensive risk assessment. The available tests demonstrate selected expected behaviors, not clinical effectiveness.

## 5. Relationship to emergency detection

The separate `EmergencyTriageAgent` uses a fixed list of emergency terms and checks whether any term occurs in the user's query.

This is useful for basic demonstration routing, but it may miss emergency descriptions that use unfamiliar wording. It may also match a term mentioned in a non-emergency context. It must not be treated as a reliable emergency diagnosis or screening system.

## 6. Recommended safeguards

- Present the application as an academic demonstration, not a diagnostic or treatment service.
- Keep clear advice to contact emergency services when an emergency may be occurring.
- Expand automated tests to cover paraphrases, negation, quoted text, different units, and false-positive cases.
- Evaluate safety behavior against a reviewed test set with qualified clinical input before any real-world clinical use.
- Do not rely on this reviewer as the only safety control.
- Review changes to the rules whenever agent prompts, model providers, or supported features change.

## 7. Current status

The project test suite covers selected rule matches, safe text, empty input, response replacement, and orchestrator integration. These tests are software regression checks; they do not establish clinical validity or guarantee that every unsafe response will be blocked.

# Appointment Access-Control Limitations

## Current implementation

The appointment management workflow allows users to book appointments by
entering a patient name. Rescheduling and cancellation use an appointment ID.
The inspected workflow does not establish a trusted authenticated patient
identity or enforce patient ownership in the appointment update methods.

The appointment records view displays records across patients.

## Security implications

- A patient name entered into a form is not proof of identity.
- An appointment ID is not proof of authorization.
- Rescheduling and cancellation must not be considered patient-authorized
  operations without a trusted identity and server-side ownership checks.
- Displaying all patient records can expose personal and medical information.

## Current scope

This application is an academic demonstration. The inspected appointment
workflow must not be represented as a secure multi-patient portal or used
to manage real patient appointments without appropriate access controls.

## Required work before multi-patient deployment

1. Establish a trusted authentication mechanism.
2. Associate each appointment with a stable patient account identifier.
3. Enforce ownership or explicitly authorized staff permissions on the
   server side for reads, rescheduling, and cancellation.
4. Restrict appointment listings to records the authenticated user is
   authorized to view.
5. Add tests proving that unauthorized users cannot read, reschedule, or
   cancel another patient's appointment.
6. Verify access-control behavior across every relevant application path.

A patient-entered name or appointment ID alone must never be treated as
authentication or authorization.

## Verification status

This document records limitations identified during code inspection.
It does not establish that authentication or authorization is absent from
every possible code path, and it does not constitute a security audit.

-- MediAgent AI
-- Migration 001: Initial PostgreSQL Schema

-- 1. Users
CREATE TABLE users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Patients
CREATE TABLE patients (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE,

    date_of_birth DATE,
    gender TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_patients_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

-- 3. Medical Specialties
CREATE TABLE specialties (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

-- 4. Doctors
CREATE TABLE doctors (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    phone TEXT,

    specialty_id BIGINT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_doctors_specialty
        FOREIGN KEY (specialty_id)
        REFERENCES specialties(id)
        ON DELETE RESTRICT
);

-- 5. Doctor Availability
CREATE TABLE doctor_availability (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    doctor_id BIGINT NOT NULL,
    available_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,

    CONSTRAINT fk_availability_doctor
        FOREIGN KEY (doctor_id)
        REFERENCES doctors(id)
        ON DELETE CASCADE,

    CONSTRAINT chk_availability_time
        CHECK (end_time > start_time),

    CONSTRAINT uq_doctor_availability
        UNIQUE (
            doctor_id,
            available_date,
            start_time,
            end_time
        )
);

-- 6. Appointments
CREATE TABLE appointments (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    patient_id BIGINT NOT NULL,
    doctor_id BIGINT NOT NULL,

    appointment_date TIMESTAMPTZ NOT NULL,

    reason TEXT,

    status TEXT NOT NULL DEFAULT 'scheduled',

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_appointments_patient
        FOREIGN KEY (patient_id)
        REFERENCES patients(id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_appointments_doctor
        FOREIGN KEY (doctor_id)
        REFERENCES doctors(id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_appointment_status
        CHECK (
            status IN (
                'scheduled',
                'completed',
                'cancelled',
                'rescheduled'
            )
        ),

    CONSTRAINT uq_doctor_appointment_time
        UNIQUE (
            doctor_id,
            appointment_date
        )
);

-- 7. Support Tickets
CREATE TABLE support_tickets (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    patient_id BIGINT NOT NULL,

    issue TEXT NOT NULL,

    priority TEXT NOT NULL DEFAULT 'normal',

    status TEXT NOT NULL DEFAULT 'open',

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_tickets_patient
        FOREIGN KEY (patient_id)
        REFERENCES patients(id)
        ON DELETE CASCADE,

    CONSTRAINT chk_ticket_priority
        CHECK (
            priority IN (
                'low',
                'normal',
                'high',
                'urgent'
            )
        ),

    CONSTRAINT chk_ticket_status
        CHECK (
            status IN (
                'open',
                'in_progress',
                'resolved',
                'closed'
            )
        )
);

-- 8. Medical Reports
CREATE TABLE medical_reports (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    patient_id BIGINT NOT NULL,

    title TEXT NOT NULL,
    report_text TEXT NOT NULL,
    summary TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_reports_patient
        FOREIGN KEY (patient_id)
        REFERENCES patients(id)
        ON DELETE CASCADE
);

-- 9. Agent/User Interactions
CREATE TABLE interactions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    patient_id BIGINT,

    task TEXT NOT NULL,
    agent TEXT NOT NULL,
    user_input TEXT NOT NULL,
    response TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_interactions_patient
        FOREIGN KEY (patient_id)
        REFERENCES patients(id)
        ON DELETE SET NULL
);

-- Indexes for commonly searched columns

CREATE INDEX idx_appointments_patient
    ON appointments(patient_id);

CREATE INDEX idx_appointments_doctor
    ON appointments(doctor_id);

CREATE INDEX idx_appointments_date
    ON appointments(appointment_date);

CREATE INDEX idx_reports_patient
    ON medical_reports(patient_id);

CREATE INDEX idx_tickets_patient
    ON support_tickets(patient_id);

CREATE INDEX idx_interactions_patient
    ON interactions(patient_id);

CREATE INDEX idx_interactions_created_at
    ON interactions(created_at);
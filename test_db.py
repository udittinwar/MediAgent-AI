import os
import psycopg

from db import get_connection, get_or_create_patient, get_or_create_doctor


def test_database_connection():
    """Test that PostgreSQL is reachable."""
    with get_connection() as conn:
        result = conn.execute("SELECT 1 AS value").fetchone()
        assert result["value"] == 1

    print("✅ Database connection test passed")


def test_patient_creation():
    """Test patient creation and duplicate prevention."""
    with get_connection() as conn:
        patient_id_1 = get_or_create_patient(conn, "Test Patient")

        patient_id_2 = get_or_create_patient(conn, "Test Patient")

        assert patient_id_1 == patient_id_2

    print("✅ Patient creation test passed")


def test_doctor_creation():
    """Test specialty and doctor creation."""
    with get_connection() as conn:
        doctor_id = get_or_create_doctor(
            conn,
            "Dr. Test Doctor",
            "General Medicine",
        )

        assert doctor_id is not None

        doctor = conn.execute(
            """
            SELECT d.id, d.name, s.name AS specialty
            FROM doctors d
            JOIN specialties s ON s.id = d.specialty_id
            WHERE d.id = %s
            """,
            (doctor_id,),
        ).fetchone()

        assert doctor is not None
        assert doctor["name"] == "Dr. Test Doctor"
        assert doctor["specialty"] == "General Medicine"

    print("✅ Doctor creation test passed")


def test_appointment_creation():
    """Test that an appointment can be inserted."""
    with get_connection() as conn:
        patient_id = get_or_create_patient(conn, "Appointment Test Patient")

        doctor_id = get_or_create_doctor(
            conn,
            "Dr. Appointment Test",
            "Cardiology",
        )

        appointment_date = "2099-01-01 10:00:00+05:30"

        row = conn.execute(
            """
            INSERT INTO appointments (
                patient_id,
                doctor_id,
                appointment_date,
                reason,
                status
            )
            VALUES (%s, %s, %s, %s, 'scheduled')
            RETURNING id
            """,
            (
                patient_id,
                doctor_id,
                appointment_date,
                "Automated database test",
            ),
        ).fetchone()

        assert row["id"] is not None

    print("✅ Appointment creation test passed")


def test_duplicate_appointment_is_rejected():
    """Test the database UNIQUE constraint on doctor/date."""
    with get_connection() as conn:
        patient_id = get_or_create_patient(conn, "Duplicate Test Patient")

        doctor_id = get_or_create_doctor(
            conn,
            "Dr. Duplicate Test",
            "Neurology",
        )

        appointment_date = "2099-02-01 11:00:00+05:30"

        conn.execute(
            """
            INSERT INTO appointments (
                patient_id,
                doctor_id,
                appointment_date,
                reason,
                status
            )
            VALUES (%s, %s, %s, %s, 'scheduled')
            """,
            (
                patient_id,
                doctor_id,
                appointment_date,
                "First appointment",
            ),
        )

        duplicate_rejected = False

        try:
            conn.execute(
                """
                INSERT INTO appointments (
                    patient_id,
                    doctor_id,
                    appointment_date,
                    reason,
                    status
                )
                VALUES (%s, %s, %s, %s, 'scheduled')
                """,
                (
                    patient_id,
                    doctor_id,
                    appointment_date,
                    "Duplicate appointment",
                ),
            )
        except psycopg.errors.UniqueViolation:
            duplicate_rejected = True
            conn.rollback()

        assert duplicate_rejected

    print("✅ Duplicate appointment protection test passed")


def test_foreign_key_protection():
    """Test that invalid patient IDs cannot create appointments."""
    with get_connection() as conn:
        doctor_id = get_or_create_doctor(
            conn,
            "Dr. Foreign Key Test",
            "Dermatology",
        )

        foreign_key_rejected = False

        try:
            conn.execute(
                """
                INSERT INTO appointments (
                    patient_id,
                    doctor_id,
                    appointment_date,
                    reason,
                    status
                )
                VALUES (%s, %s, %s, %s, 'scheduled')
                """,
                (
                    999999999,
                    doctor_id,
                    "2099-03-01 12:00:00+05:30",
                    "Foreign key test",
                ),
            )
        except psycopg.errors.ForeignKeyViolation:
            foreign_key_rejected = True
            conn.rollback()

        assert foreign_key_rejected

    print("✅ Foreign key protection test passed")


if __name__ == "__main__":
    print("\n========================================")
    print("   MediAgent AI Database Tests")
    print("========================================\n")

    test_database_connection()
    test_patient_creation()
    test_doctor_creation()
    test_appointment_creation()
    test_duplicate_appointment_is_rejected()
    test_foreign_key_protection()

    print("\n========================================")
    print("🎉 ALL DATABASE TESTS PASSED")
    print("========================================")
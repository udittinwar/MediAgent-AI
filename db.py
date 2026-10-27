import os
import psycopg
from psycopg.rows import dict_row


def get_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "mediagent"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        row_factory=dict_row,
    )


def get_or_create_patient(conn, name: str) -> int:
    """Find a patient by name or create a new patient record."""
    name = name.strip()

    email = f"{name.lower().replace(' ', '.')}@mediagent.local"

    user = conn.execute(
        """
        SELECT id
        FROM users
        WHERE name = %s
        LIMIT 1
        """,
        (name,),
    ).fetchone()

    if user:
        user_id = user["id"]
    else:
        user = conn.execute(
            """
            INSERT INTO users (name, email)
            VALUES (%s, %s)
            RETURNING id
            """,
            (name, email),
        ).fetchone()
        user_id = user["id"]

    patient = conn.execute(
        """
        SELECT id
        FROM patients
        WHERE user_id = %s
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()

    if patient:
        return patient["id"]

    patient = conn.execute(
        """
        INSERT INTO patients (user_id)
        VALUES (%s)
        RETURNING id
        """,
        (user_id,),
    ).fetchone()

    return patient["id"]


def get_or_create_doctor(conn, name: str, specialty: str) -> int:
    """Find a doctor by name or create the required specialty/doctor."""
    specialty_row = conn.execute(
        """
        SELECT id
        FROM specialties
        WHERE name = %s
        LIMIT 1
        """,
        (specialty,),
    ).fetchone()

    if specialty_row:
        specialty_id = specialty_row["id"]
    else:
        specialty_row = conn.execute(
            """
            INSERT INTO specialties (name)
            VALUES (%s)
            RETURNING id
            """,
            (specialty,),
        ).fetchone()
        specialty_id = specialty_row["id"]

    doctor = conn.execute(
        """
        SELECT id
        FROM doctors
        WHERE name = %s
        LIMIT 1
        """,
        (name,),
    ).fetchone()

    if doctor:
        return doctor["id"]

    doctor = conn.execute(
        """
        INSERT INTO doctors (name, specialty_id)
        VALUES (%s, %s)
        RETURNING id
        """,
        (name, specialty_id),
    ).fetchone()

    return doctor["id"]


if __name__ == "__main__":
    try:
        with get_connection() as conn:
            print("PostgreSQL connection successful!")
    except Exception as e:
        print("PostgreSQL connection failed:")
        print(e)
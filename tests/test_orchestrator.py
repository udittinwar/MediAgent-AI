
import ast
import contextlib
import io
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SOURCE = Path(__file__).resolve().parents[1] / "app_groq.py"


@dataclass
class AgentResult:
    task: str
    agent: str
    response: str
    page: str
    data: dict[str, Any] = field(default_factory=dict)
    safety_status: str = "PASS"
    safety_notes: list[str] = field(default_factory=list)


class FakeAgent:
    name = "Fake Agent"

    def run(self, *args, **kwargs):
        return AgentResult(
            task="Test request",
            agent=self.name,
            response="A valid test response.",
            page="AI Assistant",
        )


class FakeEmergencyAgent(FakeAgent):
    name = "Emergency Agent"

    @staticmethod
    def is_emergency(query):
        return "chest pain" in query.lower()

    def run(self, query):
        return AgentResult(
            task="Emergency / urgent escalation",
            agent=self.name,
            response="Contact local emergency services immediately.",
            page="AI Assistant",
        )


namespace = {
    "AgentResult": AgentResult,
    "BaseAgent": object,
    "ClinicalSafetyReviewerAgent": type(
    "ClinicalSafetyReviewerAgent",
    (),
    {
        "sanitize": staticmethod(
            lambda text: (text, "PASS", [])
        )
    },
),
    "EmergencyTriageAgent": FakeEmergencyAgent,
    "PatientAssistantAgent": FakeAgent,
    "SymptomTriageAgent": FakeAgent,
    "DoctorRecommendationAgent": FakeAgent,
    "AppointmentAgent": FakeAgent,
    "MedicalReportAgent": FakeAgent,
    "MedicationInfoAgent": FakeAgent,
    "PatientEducationAgent": FakeAgent,
    "CustomerSupportAgent": FakeAgent,
    "FollowUpAgent": FakeAgent,
    "insert_interaction": lambda *args: None,
}

tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
node = next(
    item for item in tree.body
    if isinstance(item, ast.ClassDef)
    and item.name == "SupervisorAgent"
)
module = ast.Module(body=[node], type_ignores=[])
exec(
    compile(ast.fix_missing_locations(module), str(SOURCE), "exec"),
    namespace,
)

Supervisor = namespace["SupervisorAgent"]


class OrchestratorFailureTests(unittest.TestCase):
    def setUp(self):
        namespace["insert_interaction"] = lambda *args: None
        self.supervisor = Supervisor()

    def test_agent_exception_returns_controlled_error(self):
        class BrokenAgent:
            def run(self, *args, **kwargs):
                raise RuntimeError("internal secret details")

        self.supervisor.patient = BrokenAgent()
        result = self.supervisor.run("Hello")

        self.assertEqual(result.safety_status, "ERROR")
        self.assertEqual(
            result.data.get("error_code"),
            "AGENT_EXECUTION_FAILED",
        )
        self.assertNotIn("internal secret details", result.response)

    def test_invalid_agent_result_returns_controlled_error(self):
        class InvalidAgent:
            def run(self, *args, **kwargs):
                return {"response": "unexpected object"}

        self.supervisor.patient = InvalidAgent()
        result = self.supervisor.run("Hello")

        self.assertEqual(result.safety_status, "ERROR")
        self.assertEqual(
            result.data.get("error_code"),
            "AGENT_EXECUTION_FAILED",
        )

    def test_logging_failure_preserves_successful_response(self):
        def broken_logger(*args):
            raise RuntimeError("database credentials must stay private")

        namespace["insert_interaction"] = broken_logger

        with contextlib.redirect_stdout(io.StringIO()):
            result = self.supervisor.run("Hello")

        self.assertEqual(result.response, "A valid test response.")
        self.assertEqual(result.safety_status, "PASS")

    def test_emergency_still_routes_to_emergency_agent(self):
        result = self.supervisor.run("I have chest pain")

        self.assertEqual(result.agent, "Emergency Agent")
        self.assertIn("emergency services", result.response.lower())

    
    def test_emergency_takes_priority_over_appointment_keywords(self):
        result = self.supervisor.run(
            "I have chest pain and need an appointment"
        )

        self.assertEqual(result.agent, "Emergency Agent")
        self.assertIn("emergency services", result.response.lower())

    def test_successful_agent_result_preserves_safety_metadata(self):
        class SafetyFlaggedAgent:
            def run(self, *args, **kwargs):
                return AgentResult(
                    task="Test request",
                    agent="Safety Flagged Agent",
                    response="Please consult a qualified healthcare professional.",
                    page="AI Assistant",
                    safety_status="NEEDS_REVISION",
                    safety_notes=["Test safety flag"],
                )

        self.supervisor.patient = SafetyFlaggedAgent()
        result = self.supervisor.run("Hello")

        self.assertEqual(result.safety_status, "NEEDS_REVISION")
        self.assertEqual(result.safety_notes, ["Test safety flag"])

    
    def test_flagged_response_is_sanitized_before_return(self):
        original_reviewer = namespace["ClinicalSafetyReviewerAgent"]

        class FlaggedReviewer:
            @staticmethod
            def sanitize(text):
                return (
                    "Please consult a qualified healthcare professional.",
                    "NEEDS_REVISION",
                    ["Unsafe medical instruction detected"],
                )

        class UnsafeAgent:
            def run(self, *args, **kwargs):
                return AgentResult(
                    task="Test request",
                    agent="Unsafe Agent",
                    response="Unsafe response for testing.",
                    page="AI Assistant",
                )

        try:
            namespace["ClinicalSafetyReviewerAgent"] = FlaggedReviewer
            self.supervisor.patient = UnsafeAgent()

            result = self.supervisor.run("Hello")

            self.assertEqual(
                result.response,
                "Please consult a qualified healthcare professional.",
            )
            self.assertEqual(result.safety_status, "NEEDS_REVISION")
            self.assertIn(
                "Unsafe medical instruction detected",
                result.safety_notes,
            )
        finally:
            namespace["ClinicalSafetyReviewerAgent"] = original_reviewer

    
    def test_appointment_request_reaches_appointment_agent(self):
        class AppointmentSpy:
            called = False

            def run(self, query):
                self.called = True
                return AgentResult(
                    task="Appointment request",
                    agent="Appointment Spy",
                    response="Appointment agent reached.",
                    page="Appointments",
                )

        spy = AppointmentSpy()
        self.supervisor.appointment = spy

        result = self.supervisor.run("I need to book an appointment")

        self.assertTrue(spy.called)
        self.assertEqual(result.agent, "Appointment Spy")
        self.assertEqual(result.response, "Appointment agent reached.")

    
    def test_followup_request_reaches_followup_agent(self):
        class FollowUpSpy:
            called = False

            def run(self, query):
                self.called = True
                return AgentResult(
                    task="Follow-up request",
                    agent="Follow-up Spy",
                    response="Follow-up agent reached.",
                    page="Follow-up",
                )

        spy = FollowUpSpy()
        self.supervisor.followup = spy

        result = self.supervisor.run(
            "What should I do after my appointment?"
        )

        self.assertTrue(spy.called)
        self.assertEqual(result.agent, "Follow-up Spy")
        self.assertEqual(result.response, "Follow-up agent reached.")

    
    def test_doctor_request_reaches_doctor_agent(self):
        class DoctorSpy:
            called = False

            def run(self, query):
                self.called = True
                return AgentResult(
                    task="Doctor recommendation",
                    agent="Doctor Spy",
                    response="Doctor agent reached.",
                    page="Find a Doctor",
                )

        spy = DoctorSpy()
        self.supervisor.doctor = spy

        result = self.supervisor.run("Help me find a cardiologist")

        self.assertTrue(spy.called)
        self.assertEqual(result.agent, "Doctor Spy")
        self.assertEqual(result.response, "Doctor agent reached.")

    
    def test_medication_request_reaches_medication_agent(self):
        class MedicationSpy:
            called = False
            received_args = None

            def run(self, *args):
                self.called = True
                self.received_args = args
                return AgentResult(
                    task="Medication information",
                    agent="Medication Spy",
                    response="Medication agent reached.",
                    page="Medication Info",
                )

        spy = MedicationSpy()
        self.supervisor.medication = spy

        result = self.supervisor.run("What are the side effects of this medicine?")

        self.assertTrue(spy.called)
        self.assertEqual(len(spy.received_args), 2)
        self.assertEqual(spy.received_args[0], "Not specified")
        self.assertEqual(result.agent, "Medication Spy")

    
    def test_report_request_directs_user_to_medical_reports_page(self):
        class ReportSpy:
            called = False

            def run(self, *args, **kwargs):
                self.called = True
                return AgentResult(
                    task="Medical report summarization",
                    agent="Report Spy",
                    response="Unexpected call",
                    page="Medical Reports",
                )

        spy = ReportSpy()
        self.supervisor.report = spy

        result = self.supervisor.run("Please explain my blood report")

        self.assertFalse(
            spy.called,
            "The orchestrator must not call the report agent without report text.",
        )
        self.assertIn("Medical Reports", result.response)
        self.assertIn("upload", result.response.lower())
        self.assertEqual(result.page, "Medical Reports")

    def test_support_request_reaches_support_agent(self):
        class SupportSpy:
            called = False

            def run(self, query):
                self.called = True
                return AgentResult(
                    task="Support request",
                    agent="Support Spy",
                    response="Support agent reached.",
                    page="Support",
                )

        spy = SupportSpy()
        self.supervisor.support = spy

        result = self.supervisor.run("I need help with a payment issue")

        self.assertTrue(spy.called)
        self.assertEqual(result.agent, "Support Spy")
        self.assertEqual(result.response, "Support agent reached.")


    
class ClinicalSafetyReviewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = SOURCE.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)

        reviewer_node = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "ClinicalSafetyReviewerAgent"
        )

        isolated_module = ast.Module(
            body=[reviewer_node],
            type_ignores=[],
        )

        reviewer_namespace = {
            "BaseAgent": object,
            "re": __import__("re"),
            "Tuple": __import__("typing").Tuple,
            "List": __import__("typing").List,
        }

        exec(
            compile(
                ast.fix_missing_locations(isolated_module),
                str(SOURCE),
                "exec",
            ),
            reviewer_namespace,
        )

        cls.reviewer = reviewer_namespace[
            "ClinicalSafetyReviewerAgent"
        ]

    def test_unsafe_dosing_instruction_is_flagged(self):
        status, issues = self.reviewer.review(
            "Take 20 mg immediately."
        )

        self.assertEqual(status, "NEEDS_REVISION")
        self.assertIn("Specific dosing instruction", issues)

    def test_definitive_diagnosis_is_flagged(self):
        status, issues = self.reviewer.review(
            "You definitely have diabetes."
        )

        self.assertEqual(status, "NEEDS_REVISION")
        self.assertIn("Definitive diagnosis language", issues)

    def test_safe_general_text_passes(self):
        text = (
            "This information may help you prepare questions "
            "for your healthcare professional."
        )

        status, issues = self.reviewer.review(text)

        self.assertEqual(status, "PASS")
        self.assertEqual(issues, [])

    def test_unsafe_response_is_replaced_with_safe_message(self):
        safe_response, status, issues = self.reviewer.sanitize(
            "Stop taking your medication immediately."
        )

        self.assertEqual(status, "NEEDS_REVISION")
        self.assertNotIn("Stop taking your medication", safe_response)
        self.assertIn("qualified healthcare professional", safe_response)
        self.assertTrue(issues)

    def test_empty_text_does_not_crash(self):
        status, issues = self.reviewer.review("")

        self.assertEqual(status, "PASS")
        self.assertEqual(issues, [])

if __name__ == "__main__":
    unittest.main()

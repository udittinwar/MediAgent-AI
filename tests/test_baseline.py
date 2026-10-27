import ast
import re
import unittest
from pathlib import Path
from typing import Any, Dict, List, Tuple

SOURCE = Path(__file__).resolve().parents[1] / "app_groq.py"


class AgentResult:
    pass


class BaseAgent:
    pass


namespace = {
    "re": re,
    "List": List,
    "Tuple": Tuple,
    "Any": Any,
    "Dict": Dict,
    "AgentResult": AgentResult,
    "BaseAgent": BaseAgent,
}


def load_class(class_name):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    node = next(
        item for item in tree.body
        if isinstance(item, ast.ClassDef) and item.name == class_name
    )
    module = ast.Module(body=[node], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)


load_class("ClinicalSafetyReviewerAgent")
load_class("EmergencyTriageAgent")
load_class("SupervisorAgent")

Safety = namespace["ClinicalSafetyReviewerAgent"]
Emergency = namespace["EmergencyTriageAgent"]
Supervisor = namespace["SupervisorAgent"]


class RoutingTests(unittest.TestCase):
    def test_emergency_detected(self):
        self.assertTrue(Emergency.is_emergency("I have chest pain"))

    def test_emergency_has_priority(self):
        self.assertEqual(
            Supervisor.route_task("I have chest pain and need an appointment"),
            "emergency",
        )

    def test_report_route(self):
        self.assertEqual(Supervisor.route_task("Explain my blood report"), "report")

    def test_appointment_route(self):
        self.assertEqual(Supervisor.route_task("Book an appointment"), "appointment")

    def test_doctor_route(self):
        self.assertEqual(Supervisor.route_task("Find a cardiologist"), "doctor")

    def test_medication_route(self):
        self.assertEqual(Supervisor.route_task("What are medication side effects?"), "medication")

    def test_support_route(self):
        self.assertEqual(Supervisor.route_task("I have a payment issue"), "support")

    def test_symptom_route(self):
        self.assertEqual(Supervisor.route_task("I have a fever"), "symptom")

    def test_education_route(self):
        self.assertEqual(Supervisor.route_task("Explain what diabetes is"), "education")

    def test_followup_route(self):
        self.assertEqual(Supervisor.route_task("What should I monitor after my appointment?"), "followup")

    def test_default_route(self):
        self.assertEqual(Supervisor.route_task("Hello"), "patient")


class SafetyTests(unittest.TestCase):
    def test_flags_definitive_diagnosis(self):
        status, issues = Safety.review("You definitely have flu")
        self.assertEqual(status, "NEEDS_REVISION")
        self.assertTrue(issues)

    def test_flags_specific_dose(self):
        status, issues = Safety.review("Take 500 mg now")
        self.assertEqual(status, "NEEDS_REVISION")
        self.assertTrue(issues)

    def test_safe_text_passes(self):
        status, issues = Safety.review(
            "Symptoms can have several causes. Consult a qualified clinician."
        )
        self.assertEqual(status, "PASS")
        self.assertEqual(issues, [])

    def test_flagged_response_gets_safe_replacement(self):
        cleaned, status, issues = Safety.sanitize("Take 500 mg now")
        self.assertEqual(status, "NEEDS_REVISION")
        self.assertTrue(issues)
        self.assertNotIn("Take 500 mg now", cleaned)
        self.assertIn("qualified healthcare professional", cleaned)

    def test_flagged_response_is_replaced(self):
        risky_text = "You definitely have flu. Take 20 mg now."
        cleaned, status, issues = Safety.sanitize(risky_text)

        self.assertEqual(status, "NEEDS_REVISION")
        self.assertTrue(issues)
        self.assertNotIn("You definitely have flu", cleaned)
        self.assertNotIn("Take 20 mg", cleaned)
        self.assertIn("qualified healthcare professional", cleaned)

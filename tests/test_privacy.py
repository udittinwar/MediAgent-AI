
import ast
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch


APP_FILE = Path(__file__).resolve().parents[1] / "app_groq.py"


def load_insert_interaction():
    source = APP_FILE.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)

    function_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "insert_interaction"
    )

    isolated_module = ast.Module(
        body=[function_node],
        type_ignores=[],
    )

    namespace = {
        "datetime": datetime,
        "db_connect": MagicMock(),
    }

    exec(compile(isolated_module, str(APP_FILE), "exec"), namespace)

    return namespace["insert_interaction"], namespace["db_connect"]


class InteractionPrivacyTests(unittest.TestCase):
    def test_raw_conversation_is_not_persisted(self):
        insert_interaction, mock_db_connect = load_insert_interaction()

        connection = MagicMock()
        mock_db_connect.return_value.__enter__.return_value = connection

        sensitive_query = "My private symptom details: PRIVATE_QUERY_123"
        sensitive_response = "Private medical advice: PRIVATE_RESPONSE_456"

        insert_interaction(
            "Symptom request",
            "Symptom Agent",
            sensitive_query,
            sensitive_response,
        )

        parameters = connection.execute.call_args.args[1]

        self.assertEqual(parameters[0], "Symptom request")
        self.assertEqual(parameters[1], "Symptom Agent")
        self.assertEqual(parameters[2], "[REDACTED]")
        self.assertEqual(parameters[3], "[REDACTED]")

        self.assertNotIn(sensitive_query, parameters)
        self.assertNotIn(sensitive_response, parameters)

        connection.commit.assert_called_once()


class MedicalReportPrivacyTests(unittest.TestCase):
    @patch("app_groq.llm_chat")
    @patch("app_groq.db_connect")
    def test_raw_report_is_not_persisted_but_summary_is(
        self,
        mock_db_connect,
        mock_llm_chat,
    ):
        import app_groq

        # Mock the database connection so no real database file is created.
        connection = MagicMock()
        cursor = MagicMock()
        cursor.lastrowid = 123

        connection.__enter__.return_value = connection
        connection.execute.return_value = cursor
        mock_db_connect.return_value.__enter__.return_value = connection

        # Mock the AI response so no external API call is made.
        generated_summary = "Summary preserved for clinician review."
        mock_llm_chat.return_value = generated_summary

        private_report = (
            "CONFIDENTIAL_REPORT_MARKER_123 "
            "Patient's private medical details"
        )

        agent = app_groq.MedicalReportAgent()

        result = agent.run(
            private_report,
            title="Privacy Test",
        )

        # Inspect the parameters sent to the database INSERT.
        connection.execute.assert_called_once()
        query, parameters = connection.execute.call_args.args

        self.assertIn("INSERT INTO reports", query)
        self.assertEqual(parameters[0], "Privacy Test")
        self.assertEqual(parameters[1], "[NOT STORED]")
        self.assertEqual(parameters[2], generated_summary)

        # Verify the original report was not included in stored parameters.
                # Verify the original report is not stored in the database.
        self.assertNotIn(private_report, parameters)
        self.assertNotIn("CONFIDENTIAL_REPORT_MARKER_123", parameters)

        # The report is sent to the configured AI-provider abstraction
        # for analysis. This test mocks the call, so no external request
        # is made.
        mock_llm_chat.assert_called_once()
        _, submitted_prompt, _ = mock_llm_chat.call_args.args[:3]
        self.assertIn("CONFIDENTIAL_REPORT_MARKER_123", submitted_prompt)
        self.assertIn("Patient's private medical details", submitted_prompt)

        # Verify the generated summary is returned to the caller.
        self.assertEqual(result.response, generated_summary)
        self.assertEqual(result.data["report_id"], 123)

        connection.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()

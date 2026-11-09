#!/usr/bin/env python3
"""The create-validation loop, with no network and no credential store."""

from __future__ import annotations

import io
import json
import os
import socket
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import qb_common  # noqa: E402,F401  (puts the QBL library on sys.path)
import qb_auth  # noqa: E402
import qb_probe  # noqa: E402
import qb_solutions  # noqa: E402
import qb_update  # noqa: E402
import cleanup_ledger  # noqa: E402
import build_qbl  # noqa: E402


class FakeKeystore:
    def __init__(self, secret=None, realm=None):
        self.secret, self.realm = secret, realm
        self.reads = 0
        self.writes = []

    def store_name(self):
        return "fake store"

    def read_secret(self, service, account):
        self.reads += 1
        return self.secret

    def exists(self, service, account):
        return self.secret is not None

    def describe(self, service, account):
        return (self.secret is not None, self.realm)

    def write(self, service, account, secret, realm):
        self.secret, self.realm = secret, realm
        self.writes.append((service, account, realm))
        return True

    def delete(self, service, account):
        self.secret = None
        return True


def patched_keystore(fake):
    return mock.patch.object(qb_auth, "_keystore", return_value=fake)


class AuthTests(unittest.TestCase):
    def test_a_bare_realm_gains_the_default_domain(self):
        realm = qb_auth.normalize_realm("MyRealm")
        self.assertEqual((realm.label, realm.host), ("myrealm", "myrealm.quickbase.com"))

    def test_a_full_host_is_kept(self):
        self.assertEqual(qb_auth.normalize_realm("example.quickbase.com").host,
                         "example.quickbase.com")

    def test_anything_that_is_not_a_hostname_is_refused_without_echo(self):
        for bad in ("", "https://example.quickbase.com", "a/b", "a b", "x:443", "-x", "a..b",
                    "tok_secret@x"):
            with self.assertRaises(qb_auth.AuthError) as caught:
                qb_auth.normalize_realm(bad)
            if bad:
                self.assertNotIn(bad, str(caught.exception))

    def test_the_environment_is_never_a_token_source(self):
        fake = FakeKeystore(secret=None)
        with patched_keystore(fake), mock.patch.dict(
                os.environ, {"QB_USER_TOKEN": "env-secret", "QUICKBASE_USER_TOKEN": "x"}):
            with self.assertRaises(qb_auth.AuthError):
                qb_auth.request_headers("r.example.com")

    def test_the_header_carries_the_stored_secret_and_the_full_host(self):
        fake = FakeKeystore(secret="stored-secret", realm="example.quickbase.com")
        with patched_keystore(fake):
            headers = qb_auth.request_headers("example.quickbase.com", {"Accept": "x"})
        self.assertEqual(headers["Authorization"], "QB-USER-TOKEN stored-secret")
        self.assertEqual(headers["QB-Realm-Hostname"], "example.quickbase.com")
        self.assertEqual(fake.reads, 1)

    def test_status_never_reads_the_secret(self):
        fake = FakeKeystore(secret="s", realm="demo")
        with patched_keystore(fake):
            info = qb_auth.status()
        self.assertEqual(fake.reads, 0)
        self.assertEqual(info["realm_host"], "demo.quickbase.com")

    def test_storing_writes_the_realm_with_the_token(self):
        fake = FakeKeystore()
        with patched_keystore(fake):
            realm = qb_auth.store_credentials("demo", "tok")
        self.assertEqual(realm.host, "demo.quickbase.com")
        self.assertEqual(fake.writes, [(qb_auth.SERVICE, qb_auth.ACCOUNT, "demo.quickbase.com")])

    def test_no_stored_realm_is_an_instruction(self):
        with patched_keystore(FakeKeystore()):
            with self.assertRaises(qb_auth.AuthError) as caught:
                qb_auth.stored_realm_host()
        self.assertIn("store_token.py", str(caught.exception))


class FakeResponse:
    def __init__(self, status, body):
        self.status, self._stream = status, io.BytesIO(body.encode())

    def read(self, size=-1):
        return self._stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ClientTests(unittest.TestCase):
    def _create(self, urlopen):
        fake = FakeKeystore(secret="s3", realm="example.quickbase.com")
        with patched_keystore(fake), mock.patch("urllib.request.OpenerDirector.open", side_effect=urlopen):
            return qb_solutions.create("Version: 0.15\n", realm_host="example.quickbase.com",
                                       timeout=5), fake

    def test_200_with_a_solution_id_is_created(self):
        seen = {}

        def urlopen(request, timeout):
            seen.update(headers=dict(request.header_items()), method=request.get_method(),
                        url=request.full_url, timeout=timeout)
            return FakeResponse(200, json.dumps({"solutionId": "sol-1",
                                                 "apps": [{"id": "bapp12345"}]}))

        outcome, fake = self._create(urlopen)
        self.assertTrue(outcome.clean)
        self.assertEqual((outcome.solution_id, outcome.app_ids), ("sol-1", ["bapp12345"]))
        self.assertEqual(seen["method"], "POST")
        self.assertEqual(seen["url"], "https://api.quickbase.com/v1/solutions")
        self.assertEqual(seen["headers"]["Qb-realm-hostname"], "example.quickbase.com")
        self.assertEqual(seen["timeout"], 5)
        self.assertEqual(fake.reads, 1)

    def test_4xx_with_errors_is_rejected_and_findings_are_parsed(self):
        def urlopen(request, timeout):
            raise urllib.error.HTTPError(
                request.full_url, 400, "bad", {},
                io.BytesIO(json.dumps({
                    "errors": [{"code": "BadProperty", "message": "no such thing",
                                "logicalId": "$Table_X"}],
                    "warnings": ["careful"]}).encode()))

        outcome, _ = self._create(urlopen)
        self.assertEqual(outcome.outcome, qb_solutions.REJECTED)
        self.assertEqual((outcome.error_count, outcome.warning_count), (1, 1))
        self.assertEqual(outcome.findings[0]["Location"], "$Table_X")
        self.assertFalse(outcome.clean)

    def test_a_timeout_is_an_outcome_not_an_exception(self):
        def urlopen(request, timeout):
            raise socket.timeout("timed out")

        outcome, _ = self._create(urlopen)
        self.assertEqual(outcome.outcome, qb_solutions.TIMEOUT)

    def test_a_url_error_wrapping_a_timeout_is_a_timeout(self):
        def urlopen(request, timeout):
            raise urllib.error.URLError(socket.timeout("t"))

        outcome, _ = self._create(urlopen)
        self.assertEqual(outcome.outcome, qb_solutions.TIMEOUT)

    def test_unreadable_answers_are_errors(self):
        outcome, _ = self._create(lambda r, timeout: FakeResponse(200, "<html>"))
        self.assertEqual(outcome.outcome, qb_solutions.ERROR)

    def test_app_ids_are_read_where_the_platform_puts_them(self):
        # Response bodies in the shape the Solutions API returns.
        created = qb_solutions.parse_response(200, json.dumps({
            "alias": None, "solutionId": "00000000-0000-4000-8000-000000000001",
            "warnings": [], "createdResources": {
                "apps": {"$App_Event_Planner": "bexample1"}, "pipelines": {}}}))
        self.assertEqual((created.outcome, created.app_ids), ("CREATED", ["bexample1"]))
        updated = qb_solutions.parse_response(200, json.dumps({
            "solutionId": "00000000-0000-4000-8000-000000000001", "warnings": [],
            "resources": {"apps": {"$App_Event_Planner": "bexample1"}}}),
            expect_solution_id=False, success_outcome=qb_solutions.UPDATED)
        self.assertEqual((updated.outcome, updated.app_ids), ("UPDATED", ["bexample1"]))

    def test_a_resources_value_that_is_not_a_dbid_is_not_an_app_id(self):
        # It becomes part of a link, so only a dbid-shaped value is taken.
        outcome = qb_solutions.parse_response(200, json.dumps({
            "solutionId": "s", "createdResources": {
                "apps": {"$A": "https://evil.example/x", "$B": {"id": "x"}}}}))
        self.assertEqual(outcome.app_ids, [])

    def test_a_rejection_reads_the_errors_nested_under_description(self):
        # An HTTP 400 response body in the shape the Solutions API returns.
        body = ('{"message":"Bad Request","description":{"warnings":[],"errors":['
                '"BadProperty: SummarizeBy in $Chart_Orders_by_Month at '
                'Line 783, Column 33","BadProperty: Data in '
                '$Chart_Orders_by_Month at Line 781, Column 18"]}}')
        outcome = qb_solutions.parse_response(400, body)
        self.assertEqual((outcome.outcome, outcome.error_count), (qb_solutions.REJECTED, 2))
        first = outcome.findings[0]
        self.assertEqual((first["Code"], first["Location"]),
                         ("PLT-BadProperty", "$Chart_Orders_by_Month"))
        self.assertIn("SummarizeBy", first["Problem"])
        self.assertNotIn("Bad Request", [f["Problem"] for f in outcome.findings])

    def test_nested_warnings_are_read_too(self):
        outcome = qb_solutions.parse_response(200, json.dumps({
            "solutionId": "s", "description": {"warnings": ["careful"], "errors": []}}))
        self.assertEqual((outcome.outcome, outcome.warning_count), ("CREATED", 1))

    def test_a_400_whose_description_is_an_object_without_lists_keeps_the_message(self):
        outcome = qb_solutions.parse_response(400, json.dumps(
            {"message": "Bad Request", "description": {"other": 1}}))
        self.assertEqual(outcome.findings[0]["Problem"], "Bad Request")

    def test_the_message_naming_no_resource_gets_a_hint(self):
        outcome = qb_solutions.parse_response(400, json.dumps(
            {"errors": ["failure in creating one of the resources"]}))
        self.assertTrue(outcome.hints)


def _outcome(kind, solution="sol-1", apps=("bapp12345",), errors=0):
    findings = [{"Code": "PLT-X", "Severity": "Error", "Problem": "p"}] * errors
    return qb_solutions.Outcome(kind, http=200, solution_id=solution if kind == "CREATED" else "",
                                app_ids=list(apps) if kind == "CREATED" else [],
                                findings=findings)


HOST = "example.quickbase.com"


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.path = Path(self._t.name) / "qbl-cleanup.json"

    def tearDown(self):
        self._t.cleanup()

    def record(self, purpose, outcome, intent="new", sha="a"):
        return cleanup_ledger.record(
            self.path, purpose=purpose, app_name="App", source_sha256=sha, sent_sha256=sha,
            realm_host=HOST, outcome=outcome, intent=intent)

    def test_the_latest_clean_new_create_is_the_deliverable_and_not_listed(self):
        self.record("attempt", _outcome("CREATED", "sol-1"))
        second = self.record("attempt", _outcome("CREATED", "sol-2"))
        self.assertEqual(second["purpose"], "deliverable")
        pending = cleanup_ledger.to_delete(cleanup_ledger.load(self.path))
        self.assertEqual([e["solution_id"] for e in pending], ["sol-1"])

    def test_entries_carry_the_links_hashes_and_realm(self):
        entry = self.record("validation-copy", _outcome("CREATED"), intent="edit", sha="abc")
        self.assertEqual(entry["links"], [f"https://{HOST}/nav/app/bapp12345"])
        self.assertEqual((entry["source_sha256"], entry["realm_host"], entry["outcome"]),
                         ("abc", HOST, "CREATED"))
        self.assertEqual(entry["purpose"], "validation-copy")

    def test_a_timeout_is_listed_with_the_note_and_a_rejection_is_not(self):
        timeout = self.record("attempt", _outcome("TIMEOUT"))
        self.record("attempt", _outcome("REJECTED"))
        self.assertIn("exact", timeout["note"])
        pending = cleanup_ledger.to_delete(cleanup_ledger.load(self.path))
        self.assertEqual([e["outcome"] for e in pending], ["TIMEOUT"])

    def test_the_list_is_newest_first_and_mark_deleted_removes_it(self):
        self.record("probe", _outcome("CREATED", "sol-a"))
        self.record("probe", _outcome("CREATED", "sol-b"))
        ledger = cleanup_ledger.load(self.path)
        self.assertEqual([e["solution_id"] for e in cleanup_ledger.to_delete(ledger)],
                         ["sol-b", "sol-a"])
        self.assertEqual(cleanup_ledger.mark_deleted(self.path, "sol-b"), 1)
        ledger = cleanup_ledger.load(self.path)
        self.assertEqual([e["solution_id"] for e in cleanup_ledger.to_delete(ledger)], ["sol-a"])
        self.assertIn(f"https://{HOST}/nav/app/bapp12345",
                      "\n".join(cleanup_ledger.cleanup_lines(ledger)))

    def test_a_clean_create_is_found_by_source_hash_only(self):
        self.record("validation-copy", _outcome("CREATED"), intent="edit", sha="aaa")
        ledger = cleanup_ledger.load(self.path)
        self.assertIsNotNone(cleanup_ledger.clean_create_for(ledger, "aaa"))
        self.assertIsNone(cleanup_ledger.clean_create_for(ledger, "bbb"))


def _spec(extra_table=False, dashboards=0):
    from qblparser.generation import (AppSpec, DashboardSpec, DashboardWidgetSpec, FieldSpec,
                                      RelationshipSpec, ReportSpec, TableSpec)

    tables = [TableSpec("Clients", fields=[FieldSpec("Client Name")],
                        reports=[ReportSpec("All Clients", kind="Table")]),
              TableSpec("Projects", fields=[FieldSpec("Project Name")],
                        reports=[ReportSpec("All Projects", kind="Table")])]
    if extra_table:
        tables.append(TableSpec("Notes", fields=[FieldSpec("Note")]))
    return AppSpec(
        name="Tracker", tables=tables,
        relationships=[RelationshipSpec("Clients", "Projects")],
        dashboards=[DashboardSpec(f"D{i}", widgets=[DashboardWidgetSpec(
            kind="Table", title="t", table="Clients", report="All Clients", width=6)])
            for i in range(1, dashboards + 1)])


class UpdateTests(unittest.TestCase):
    def setUp(self):
        from qblparser.generation import compile_app

        self._t = tempfile.TemporaryDirectory()
        self.dir = Path(self._t.name)
        self.document = self.dir / "app.qbl.yaml"
        self.document.write_text(qb_common.document_yaml(compile_app(_spec())))
        self.deployed = self.dir / "current.qbl.yaml"
        self.deployed.write_text(qb_common.document_yaml(compile_app(_spec(extra_table=True))))
        self.ledger = self.dir / "qbl-cleanup.json"
        self.sha = qb_common.sha256_file(self.document)

    def tearDown(self):
        self._t.cleanup()

    def clean_ledger(self, sha=None, when="2999-01-01T00:00:00+00:00", **extra):
        name = "Tracker (validation copy)"
        sent = qb_common.sha256_text(qb_common.renamed_text(
            qb_common.load_document(str(self.document)), name))
        with mock.patch.object(cleanup_ledger, "utc_now", return_value=when):
            return cleanup_ledger.record(
                self.ledger, purpose="validation-copy", app_name=name,
                source_sha256=sha or self.sha, sent_sha256=sent,
                realm_host=HOST, outcome=extra.pop("outcome", _outcome("CREATED")),
                intent="edit", **extra)

    def build_record(self, solution="sol-1", fetched=True):
        if fetched:
            qb_update.write_deployed_record(self.deployed, solution_id=solution,
                                            realm_host=HOST, qbl_version="0.15")
        qb_update.write_build_record(self.document, deployed=self.deployed)

    def guards(self, confirm="sol-1"):
        return qb_update.check_guards(solution_id="sol-1", confirm=confirm,
                                      document=self.document, ledger_path=self.ledger,
                                      realm_host=HOST)

    def test_it_refuses_without_a_matching_confirm(self):
        self.clean_ledger()
        self.build_record()
        for bad in (None, "", "sol-2"):
            with self.assertRaises(qb_update.UpdateRefused) as caught:
                self.guards(bad)
            self.assertIn("--confirm", str(caught.exception))

    def test_it_refuses_without_a_clean_ledger_entry_for_the_same_hash(self):
        self.build_record()
        with self.assertRaises(qb_update.UpdateRefused):
            self.guards()
        self.clean_ledger(sha="not-this-document")
        with self.assertRaises(qb_update.UpdateRefused) as caught:
            self.guards()
        self.assertIn("clean create", str(caught.exception))

    def test_it_refuses_a_document_whose_only_create_had_errors(self):
        self.clean_ledger(outcome=_outcome("REJECTED", errors=1))
        self.build_record()
        with self.assertRaises(qb_update.UpdateRefused):
            self.guards()

    def test_it_refuses_a_document_not_built_with_deployed(self):
        self.clean_ledger()
        qb_update.write_build_record(self.document, deployed=None)
        with self.assertRaises(qb_update.UpdateRefused) as caught:
            self.guards()
        self.assertIn("--deployed", str(caught.exception))

    def test_it_refuses_an_export_of_another_solution_or_one_not_fetched(self):
        self.clean_ledger()
        self.build_record(solution="sol-other")
        with self.assertRaises(qb_update.UpdateRefused):
            self.guards()
        qb_update.deployed_record_path(self.deployed).unlink()
        qb_update.write_build_record(self.document, deployed=self.deployed)
        with self.assertRaises(qb_update.UpdateRefused):
            self.guards()

    def test_it_refuses_when_the_document_changed_after_the_build(self):
        self.clean_ledger()
        self.build_record()
        self.document.write_text(self.document.read_text() + "\n# edited\n")
        with self.assertRaises(qb_update.UpdateRefused):
            self.guards()

    def test_every_guard_met_passes_and_the_preview_lists_what_is_deleted(self):
        self.clean_ledger()
        self.build_record()
        checked = self.guards()
        rows = qb_update.deletion_preview(qb_common.load_document(str(self.document)),
                                          qb_common.load_document(str(checked.deployed_export)))
        self.assertTrue(any("Notes" in row["path"] for row in rows), rows)
        text = "\n".join(qb_update.preview_lines(rows))
        self.assertIn("deletes", text)

    def test_the_command_refuses_with_a_non_zero_exit(self):
        args = build_qbl.argparse.Namespace(
            solution_id="sol-1", document=str(self.document), confirm=None,
            ledger=str(self.ledger), realm=None, timeout=5, format="text")
        with mock.patch("sys.stderr"):
            self.assertNotEqual(build_qbl._update(args), 0)


class RelayTests(unittest.TestCase):
    TEXT = "Version: 0.15\nResources: {}\n"

    def test_a_wrapped_response_becomes_the_same_outcome_as_a_call(self):
        digest = qb_common.sha256_text(self.TEXT)
        outcome = qb_solutions.ingest_platform_response(
            {"http_status": 200, "timed_out": False, "sha256": digest,
             "body": {"solutionId": "sol-9", "apps": ["bapp99999"]}}, self.TEXT)
        self.assertTrue(outcome.clean)
        self.assertEqual((outcome.solution_id, outcome.app_ids), ("sol-9", ["bapp99999"]))

    def test_the_raw_api_json_is_accepted_unwrapped(self):
        rejected = qb_solutions.ingest_platform_response(
            {"errors": [{"message": "bad"}], "warnings": []}, self.TEXT)
        self.assertEqual(rejected.outcome, qb_solutions.REJECTED)

    def test_a_timeout_flag_is_a_timeout(self):
        outcome = qb_solutions.ingest_platform_response({"timedOut": True}, self.TEXT)
        self.assertEqual(outcome.outcome, qb_solutions.TIMEOUT)

    def test_a_digest_that_is_not_the_submissions_is_refused(self):
        with self.assertRaises(qb_solutions.RelayError):
            qb_solutions.ingest_platform_response(
                {"sha256": "0" * 64, "http_status": 200, "body": {"solutionId": "s"}}, self.TEXT)

    def test_a_response_that_is_not_json_is_refused(self):
        with self.assertRaises(qb_solutions.RelayError):
            qb_solutions.ingest_platform_response("not json", self.TEXT)


class ProbeTests(unittest.TestCase):
    def test_the_ladder_is_a_floor_then_one_cumulative_rung_per_family(self):
        ladder = qb_probe.build_ladder(_spec(dashboards=2), "T")
        self.assertEqual([r.family for r in ladder], ["floor", "reports", "dashboards"])
        floor, reports, dashboards = ladder
        self.assertEqual([len(t.reports) for t in floor.spec.tables], [0, 0])
        self.assertEqual(floor.spec.dashboards, [])
        self.assertEqual(len(floor.spec.tables), 2)
        self.assertEqual(len(floor.spec.relationships), 1)
        self.assertEqual([len(t.reports) for t in reports.spec.tables], [1, 1])
        self.assertEqual(len(reports.spec.dashboards), 0)
        self.assertEqual(len(dashboards.spec.dashboards), 2)
        self.assertEqual(dashboards.spec.name, "QBL probe T rung 2: dashboards")
        self.assertEqual(floor.spec.name, "QBL probe T rung 0: floor")
        self.assertEqual(dashboards.spec.requirements, [])

    def _run(self, fails_when, spec, max_creates=12, gate_ok=True):
        calls = []

        def create(document, name, label):
            calls.append(name)
            text = qb_common.document_yaml(document)
            return _outcome("REJECTED", errors=1) if fails_when(text) else _outcome("CREATED")

        report = qb_probe.run_probe(
            spec, stamp="T", create=create,
            gates=lambda document: {"passed": gate_ok, "errors": 0 if gate_ok else 1},
            compile_fn=build_qbl.compile_app, max_creates=max_creates)
        return report, calls

    def test_it_localises_to_the_family_and_halves_to_one_item(self):
        report, calls = self._run(lambda text: "D3" in text, _spec(dashboards=3))
        self.assertEqual(report.localised_family, "dashboards")
        self.assertTrue(report.exact)
        self.assertEqual(len(report.localised_items), 1)
        self.assertIn("D3", report.localised_items[0])
        self.assertTrue(all(name.startswith("QBL probe T rung ") for name in calls))
        self.assertLessEqual(report.creates, 12)

    def test_a_failing_floor_stops_the_ladder(self):
        report, calls = self._run(lambda text: True, _spec(dashboards=1))
        self.assertTrue(report.floor_failed)
        self.assertEqual(len(calls), 1)

    def test_the_create_budget_bounds_the_probe(self):
        report, calls = self._run(lambda text: "D3" in text, _spec(dashboards=3), max_creates=3)
        self.assertLessEqual(len(calls), 3)

    def test_a_rung_that_fails_offline_is_reported_and_not_created(self):
        report, calls = self._run(lambda text: False, _spec(dashboards=1), gate_ok=False)
        self.assertEqual(calls, [])
        self.assertTrue(all(r.status == "skipped-offline" for r in report.results))

    def test_every_rung_create_is_ledgered_as_a_probe_by_the_command(self):
        with tempfile.TemporaryDirectory() as scratch:
            spec_file = Path(scratch) / "spec.py"
            spec_file.write_text("from qblparser.generation import AppSpec, TableSpec, FieldSpec\n"
                                 "SPEC = AppSpec(name='P', tables=[TableSpec('T', "
                                 "fields=[FieldSpec('N')])])\n")
            args = build_qbl.argparse.Namespace(
                spec=str(spec_file), ledger=str(Path(scratch) / "qbl-cleanup.json"), realm=None,
                timeout=5, max_creates=12,
                format="json")
            with mock.patch.object(qb_auth, "stored_realm_host", return_value=HOST), \
                    mock.patch.object(qb_solutions, "create",
                                      return_value=_outcome("CREATED", "sol-p")), \
                    mock.patch("sys.stdout"):
                build_qbl._probe(args)
            ledger = cleanup_ledger.load(Path(scratch) / "qbl-cleanup.json")
        self.assertTrue(ledger["entries"])
        self.assertEqual({e["purpose"] for e in ledger["entries"]}, {"probe"})


def _exported_shape(overrides=None):
    """A compiled app in the shape an export writes it: the name is a `!Var`.

    Every export hoists the application's name into `ParameterDefinitions` and
    may end in a `Parameters` document that overrides it. Read raw, the name is
    the mapping `{'Name': 'App_Name_1'}`.
    """
    from qblparser.generation import compile_app
    from qblparser.utils.qbl_tags import QBLTaggedMapping

    document = compile_app(_spec())
    document["ParameterDefinitions"] = {"App_Name_1": {
        "Type": "String", "Description": "Parameter for QB::Application-Name",
        "Value": "Tracker"}}
    _, app = qb_common.find_application(document)
    app["Properties"]["Name"] = QBLTaggedMapping({"Name": "App_Name_1"}).with_tag("Var")
    text = qb_common.document_yaml(document)
    if overrides:
        text += "---\nParameters:\n" + "".join(
            f"  {name}: {value}\n" for name, value in overrides.items())
    return text


class ExportedNameTests(unittest.TestCase):
    """The app name of an exported document is a `!Var`, not a string."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.dir = Path(self._t.name)

    def tearDown(self):
        self._t.cleanup()

    def load(self, text):
        path = self.dir / "exported.qbl.yaml"
        path.write_text(text)
        return qb_common.load_document(str(path))

    def test_the_name_is_read_through_the_parameter(self):
        self.assertEqual(qb_common.application_name(self.load(_exported_shape())), "Tracker")

    def test_the_trailing_parameters_document_wins(self):
        document = self.load(_exported_shape({"App_Name_1": "Tracker-DEV"}))
        self.assertEqual(qb_common.application_name(document), "Tracker-DEV")

    def test_a_rename_changes_the_parameter_value_and_keeps_the_reference(self):
        document = self.load(_exported_shape({"App_Name_1": "Tracker-DEV"}))
        text = qb_common.renamed_text(document, "Tracker (copy)")
        self.assertNotIn("{'Name'", text)
        self.assertIn("Name: !Var", text)
        reloaded = self.load(text)
        self.assertEqual(qb_common.application_name(reloaded), "Tracker (copy)")
        self.assertEqual(reloaded["ParameterDefinitions"]["App_Name_1"]["Value"],
                         "Tracker (copy)")
        self.assertEqual(reloaded.parameter_overrides, {"App_Name_1": "Tracker (copy)"})

    def test_a_literal_name_is_still_replaced_where_it_stands(self):
        from qblparser.generation import compile_app

        text = qb_common.renamed_text(compile_app(_spec()), "Tracker (copy)")
        self.assertEqual(qb_common.application_name(self.load(text)), "Tracker (copy)")

    def test_an_unresolvable_name_is_refused_rather_than_printed(self):
        text = _exported_shape().replace("App_Name_1:\n", "Other_Name:\n", 1)
        with self.assertRaises(qb_common.SkillInputError):
            qb_common.application_name(self.load(text))


class CreateCommandTests(unittest.TestCase):
    def setUp(self):
        from qblparser.generation import compile_app

        self._t = tempfile.TemporaryDirectory()
        self.dir = Path(self._t.name)
        self.document = self.dir / "app.qbl.yaml"
        self.document.write_text(qb_common.document_yaml(compile_app(_spec())))

    def tearDown(self):
        self._t.cleanup()

    def args(self, **kw):
        base = dict(document=str(self.document), intent="new", name_suffix=None,
                    write_submission=None, platform_response=None, submission=None,
                    ledger=str(self.dir / "qbl-cleanup.json"), realm=None, timeout=5,
                    format="json")
        base.update(kw)
        return build_qbl.argparse.Namespace(**base)

    def run_create(self, args, outcome):
        sent = {}

        def fake_create(text, realm_host, timeout):
            sent.update(text=text, realm=realm_host)
            return outcome

        with mock.patch.object(qb_auth, "stored_realm_host", return_value=HOST), \
                mock.patch.object(qb_solutions, "create", side_effect=fake_create), \
                mock.patch("sys.stdout"):
            code = build_qbl._create(args)
        return code, sent

    def test_a_new_clean_create_is_the_deliverable(self):
        code, sent = self.run_create(self.args(), _outcome("CREATED"))
        self.assertEqual(code, 0)
        self.assertEqual(sent["text"], self.document.read_text())
        entries = cleanup_ledger.load(self.dir / "qbl-cleanup.json")["entries"]
        self.assertEqual([e["purpose"] for e in entries], ["deliverable"])

    def test_an_edit_is_sent_as_a_marked_validation_copy(self):
        code, sent = self.run_create(self.args(intent="edit"), _outcome("CREATED"))
        self.assertEqual(code, 0)
        self.assertIn("validation copy", sent["text"])
        entries = cleanup_ledger.load(self.dir / "qbl-cleanup.json")["entries"]
        self.assertEqual(entries[0]["purpose"], "validation-copy")
        self.assertEqual(entries[0]["source_sha256"], qb_common.sha256_file(self.document))
        self.assertNotEqual(entries[0]["sent_sha256"], entries[0]["source_sha256"])
        self.assertIn("validation copy", entries[0]["app_name"])

    def test_an_exported_document_is_copied_under_its_real_name(self):
        self.document.write_text(_exported_shape())
        code, sent = self.run_create(self.args(intent="edit"), _outcome("CREATED"))
        self.assertEqual(code, 0)
        self.assertNotIn("{'Name'", sent["text"])
        path = self.dir / "sent.qbl.yaml"
        path.write_text(sent["text"])
        name = qb_common.application_name(qb_common.load_document(str(path)))
        self.assertTrue(name.startswith("Tracker (validation copy "), name)
        entry = cleanup_ledger.load(self.dir / "qbl-cleanup.json")["entries"][0]
        self.assertEqual(entry["app_name"], name)

    def test_a_name_suffix_on_an_exported_document_uses_the_real_name(self):
        self.document.write_text(_exported_shape())
        code, sent = self.run_create(self.args(name_suffix="test"), _outcome("CREATED"))
        self.assertEqual(code, 0)
        self.assertIn("Value: Tracker (test)", sent["text"])

    def test_errors_and_timeouts_exit_non_zero(self):
        for kind in ("REJECTED", "TIMEOUT"):
            code, _ = self.run_create(self.args(), _outcome(kind, errors=1))
            self.assertNotEqual(code, 0, kind)

    def test_a_document_failing_the_offline_gates_is_not_sent(self):
        broken = self.dir / "broken.qbl.yaml"
        broken.write_text(self.document.read_text().replace("QB::Field::", "QB::Fieldx::", 1))
        with mock.patch.object(qb_solutions, "create") as create, mock.patch("sys.stdout"):
            code = build_qbl._create(self.args(document=str(broken)))
        self.assertNotEqual(code, 0)
        create.assert_not_called()

    def _no_stored_token(self):
        return mock.patch.object(qb_auth, "stored_realm_host",
                                 side_effect=qb_auth.AuthError("none"))

    def test_the_relay_round_trip_ledgers_the_extension_answer(self):
        submission = self.dir / "sub.yaml"
        with self._no_stored_token(), mock.patch("sys.stdout"):
            code = build_qbl._create(self.args(write_submission=str(submission), realm=HOST))
        self.assertEqual(code, 0)
        text = submission.read_text()
        response = self.dir / "resp.json"
        response.write_text(json.dumps({
            "http_status": 200, "sha256": qb_common.sha256_text(text),
            "body": {"solutionId": "sol-r", "apps": ["bapp55555"]}}))
        with mock.patch.object(qb_solutions, "create") as create, self._no_stored_token(), \
                mock.patch("sys.stdout"):
            code = build_qbl._create(self.args(platform_response=str(response),
                                               submission=str(submission), realm=HOST))
        create.assert_not_called()
        self.assertEqual(code, 0)
        entry = cleanup_ledger.load(self.dir / "qbl-cleanup.json")["entries"][0]
        self.assertEqual((entry["solution_id"], entry["realm_host"]), ("sol-r", HOST))

    def test_a_relay_response_for_another_submission_is_refused_and_not_ledgered(self):
        submission = self.dir / "sub.yaml"
        with self._no_stored_token(), mock.patch("sys.stdout"):
            build_qbl._create(self.args(write_submission=str(submission), realm=HOST))
        response = self.dir / "resp.json"
        response.write_text(json.dumps({"http_status": 200, "sha256": "0" * 64,
                                        "body": {"solutionId": "sol-r"}}))
        with self._no_stored_token(), mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            code = build_qbl._create(self.args(platform_response=str(response),
                                               submission=str(submission), realm=HOST))
        self.assertNotEqual(code, 0)
        entries = cleanup_ledger.load(self.dir / "qbl-cleanup.json")["entries"]
        self.assertEqual([e["outcome"] for e in entries], ["PENDING"])  # request may have gone


if __name__ == "__main__":
    unittest.main()

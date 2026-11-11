"""Ledger ordering and locking, update guards, and the HTTP client's limits.

No network: `urllib.request.OpenerDirector.open` is patched wherever a request
would be made.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import qb_common  # noqa: E402,F401  (puts the QBL library on sys.path)
import qb_auth  # noqa: E402
import qb_solutions  # noqa: E402
import qb_update  # noqa: E402
import cleanup_ledger  # noqa: E402
import build_qbl  # noqa: E402
from test_builder import (FakeKeystore, FakeResponse, HOST, _outcome, _spec,  # noqa: E402
                          patched_keystore)

SKILL_DIR = Path(__file__).resolve().parent.parent
OPEN = "urllib.request.OpenerDirector.open"


def _ns(**kw):
    return build_qbl.argparse.Namespace(**kw)


class CommandCase(unittest.TestCase):
    """A built document in a scratch directory, and a way to run `create` on it."""

    def setUp(self):
        from qblparser.generation import compile_app

        self._t = tempfile.TemporaryDirectory()
        self.dir = Path(self._t.name)
        self.document = self.dir / "app.qbl.yaml"
        self.document.write_text(qb_common.document_yaml(compile_app(_spec())))
        self.ledger = self.dir / "qbl-cleanup.json"

    def tearDown(self):
        self._t.cleanup()

    def args(self, **kw):
        base = dict(document=str(self.document), intent="new", name_suffix=None,
                    write_submission=None, platform_response=None, submission=None,
                    ledger=str(self.ledger), realm=None, timeout=5, format="json")
        base.update(kw)
        return _ns(**base)

    def create(self, args, side_effect):
        with mock.patch.object(qb_auth, "stored_realm_host", return_value=HOST), \
                mock.patch.object(qb_solutions, "create", side_effect=side_effect) as create, \
                mock.patch("sys.stdout"):
            code = build_qbl._create(args)
        return code, create

    def entries(self):
        return cleanup_ledger.load(self.ledger)["entries"]


class PendingBeforeSendTests(CommandCase):
    def test_a_pending_entry_exists_during_the_request_then_is_updated_in_place(self):
        seen = []

        def fake(text, realm_host, timeout):
            seen.append(self.entries())
            return _outcome("CREATED")

        self.create(self.args(intent="edit"), fake)
        during = seen[0]
        self.assertEqual(len(during), 1)
        pending = during[0]
        self.assertEqual(pending["outcome"], "PENDING")
        self.assertIn("validation copy", pending["app_name"])
        self.assertEqual(pending["purpose"], "validation-copy")
        self.assertEqual(pending["realm_host"], HOST)
        self.assertTrue(pending["source_sha256"] and pending["sent_sha256"] and pending["time"])
        after = self.entries()
        self.assertEqual([(e["id"], e["outcome"]) for e in after], [(pending["id"], "CREATED")])

    def test_a_killed_process_leaves_a_pending_entry_that_cleanup_lists(self):
        def fake(text, realm_host, timeout):
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.create(self.args(), fake)
        entry = self.entries()[0]
        self.assertEqual(entry["outcome"], "PENDING")
        listed = cleanup_ledger.to_delete(cleanup_ledger.load(self.ledger))
        self.assertEqual([e["id"] for e in listed], [entry["id"]])
        text = "\n".join(cleanup_ledger.cleanup_lines(cleanup_ledger.load(self.ledger)))
        self.assertIn("may have completed", text)
        self.assertIn("exactly this name", text)

    def test_a_request_that_never_left_does_not_leave_a_pending_entry(self):
        def fake(text, realm_host, timeout):
            raise qb_auth.AuthError("no token")

        with self.assertRaises(qb_auth.AuthError):
            self.create(self.args(), fake)
        self.assertEqual(self.entries(), [])

    def test_a_corrupt_ledger_refuses_before_any_request(self):
        self.ledger.write_text("{not json")
        with self.assertRaises(build_qbl.SkillInputError):
            self.create(self.args(), lambda *a, **k: _outcome("CREATED"))
        # `create` was never reached
        with mock.patch.object(qb_solutions, "create") as create, \
                mock.patch.object(qb_auth, "stored_realm_host", return_value=HOST):
            with self.assertRaises(build_qbl.SkillInputError):
                build_qbl._create(self.args())
        create.assert_not_called()

    def test_probe_writes_pending_first_and_refuses_on_a_corrupt_ledger(self):
        spec_file = self.dir / "spec.py"
        spec_file.write_text("from qblparser.generation import AppSpec, TableSpec, FieldSpec\n"
                             "SPEC = AppSpec(name='P', tables=[TableSpec('T', "
                             "fields=[FieldSpec('N')])])\n")
        seen = []

        def fake(text, realm_host, timeout):
            seen.append([e["outcome"] for e in self.entries()])
            return _outcome("CREATED", "sol-p")

        args = _ns(spec=str(spec_file), ledger=str(self.ledger), realm=None, timeout=5,
                   max_creates=12, format="json")
        with mock.patch.object(qb_auth, "stored_realm_host", return_value=HOST), \
                mock.patch.object(qb_solutions, "create", side_effect=fake), \
                mock.patch("sys.stdout"):
            build_qbl._probe(args)
        self.assertEqual(seen[0], ["PENDING"])
        self.ledger.write_text("[]")
        with mock.patch.object(qb_auth, "stored_realm_host", return_value=HOST), \
                mock.patch.object(qb_solutions, "create") as create:
            with self.assertRaises(build_qbl.SkillInputError):
                build_qbl._probe(args)
        create.assert_not_called()


class LockTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.path = Path(self._t.name) / "qbl-cleanup.json"

    def tearDown(self):
        self._t.cleanup()

    def test_concurrent_writers_keep_every_entry_and_ids_unique(self):
        def work(tag):
            for i in range(15):
                cleanup_ledger.begin(self.path, purpose="probe", app_name=f"{tag}{i}",
                                     source_sha256="a", sent_sha256="b", realm_host=HOST)

        threads = [threading.Thread(target=work, args=(t,)) for t in "abcd"]
        [t.start() for t in threads]
        [t.join() for t in threads]
        entries = cleanup_ledger.load(self.path)["entries"]
        self.assertEqual(len(entries), 60)
        self.assertEqual(len({e["id"] for e in entries}), 60)

    def test_a_held_lock_blocks_then_refuses(self):
        lock = Path(str(self.path) + ".lock")
        lock.write_text("held")
        with mock.patch.object(cleanup_ledger, "LOCK_WAIT_SECONDS", 0.2):
            with self.assertRaises(build_qbl.SkillInputError):
                cleanup_ledger.begin(self.path, purpose="probe", app_name="x",
                                     source_sha256="a", sent_sha256="b", realm_host=HOST)
        self.assertTrue(lock.exists())

    def test_a_stale_lock_is_taken_over_and_the_lock_is_released(self):
        lock = Path(str(self.path) + ".lock")
        lock.write_text("dead")
        old = time.time() - cleanup_ledger.LOCK_STALE_SECONDS - 10
        os.utime(lock, (old, old))
        cleanup_ledger.begin(self.path, purpose="probe", app_name="x",
                             source_sha256="a", sent_sha256="b", realm_host=HOST)
        self.assertFalse(lock.exists())
        self.assertEqual(len(cleanup_ledger.load(self.path)["entries"]), 1)


class ToDeleteTests(unittest.TestCase):
    def test_rejected_with_ids_and_pending_are_listed_plain_rejections_are_not(self):
        def entry(i, outcome, **kw):
            base = {"id": i, "time": f"2026-01-0{i}", "purpose": "attempt", "app_name": "A",
                    "outcome": outcome, "solution_id": "", "app_ids": [], "deleted_at": ""}
            base.update(kw)
            return base

        ledger = {"entries": [
            entry(1, "REJECTED"),
            entry(2, "REJECTED", solution_id="sol-x"),
            entry(3, "REJECTED", app_ids=["bapp1"]),
            entry(4, "PENDING"),
            entry(5, "CREATED", purpose="deliverable"),
        ]}
        self.assertEqual([e["id"] for e in cleanup_ledger.to_delete(ledger)], [4, 3, 2])

    def test_a_solution_a_put_updated_is_never_listed_for_deletion(self):
        # An app edited by an approved PUT stays off the deletion list, even
        # when a newer `--intent new` create is recorded after its create.
        ledger = {"entries": [
            {"id": 1, "time": "2026-01-01", "call": "POST create", "purpose": "attempt",
             "app_name": "A", "outcome": "CREATED", "solution_id": "sol-a",
             "app_ids": ["bapp1"], "deleted_at": ""},
            {"id": 2, "time": "2026-01-02", "call": "PUT update", "purpose": "deliverable",
             "app_name": "A", "outcome": "UPDATED", "solution_id": "sol-a",
             "app_ids": [], "deleted_at": ""},
            {"id": 3, "time": "2026-01-03", "call": "POST create", "purpose": "attempt",
             "app_name": "B", "outcome": "CREATED", "solution_id": "sol-b",
             "app_ids": ["bapp2"], "deleted_at": ""},
        ]}
        self.assertEqual([e["id"] for e in cleanup_ledger.to_delete(ledger)], [3])

    def test_a_timed_out_create_sharing_a_known_apps_name_warns_not_to_delete_it(self):
        # When a timed-out create shares a name with an app that was created
        # later, the note warns instead of saying to delete "exactly this name".
        ledger = {"entries": [
            {"id": 7, "time": "2026-01-01", "call": "POST create", "purpose": "attempt",
             "app_name": "A", "outcome": "TIMEOUT", "solution_id": "", "app_ids": [],
             "links": [], "note": cleanup_ledger.TIMEOUT_NOTE, "deleted_at": ""},
            {"id": 9, "time": "2026-01-02", "call": "POST create", "purpose": "deliverable",
             "app_name": "A", "outcome": "CREATED", "solution_id": "sol-a",
             "app_ids": ["bapp1"], "links": ["https://example.quickbase.com/nav/app/bapp1"],
             "deleted_at": ""},
        ]}
        text = "\n".join(cleanup_ledger.cleanup_lines(ledger))
        self.assertIn("CAREFUL", text)
        self.assertIn("#9 (deliverable) https://example.quickbase.com/nav/app/bapp1", text)
        ledger["entries"][1]["app_name"] = "B"
        self.assertNotIn("CAREFUL", "\n".join(cleanup_ledger.cleanup_lines(ledger)))


class OneLedgerTests(CommandCase):
    def test_every_subcommand_defaults_to_the_cwd_ledger_and_accepts_ledger(self):
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        cwd = os.getcwd()
        os.chdir(other.name)
        self.addCleanup(os.chdir, cwd)
        code, _ = self.create(self.args(ledger=None), lambda *a, **k: _outcome("TIMEOUT"))
        self.assertTrue((Path(other.name) / "qbl-cleanup.json").exists())
        self.assertFalse((self.dir / "qbl-cleanup.json").exists())
        args = _ns(ledger=None, mark_deleted=None, format="json")
        self.assertEqual(build_qbl._ledger_path(args).resolve(),
                         (Path(other.name) / "qbl-cleanup.json").resolve())
        with mock.patch("sys.stdout") as out:
            build_qbl._cleanup(args)
        self.assertIn("qbl-cleanup.json", "".join(c.args[0] for c in out.write.call_args_list))
        for command in ("create", "probe", "update", "cleanup", "fetch-deployed"):
            with mock.patch("sys.stdout", new_callable=io.StringIO) as out, \
                    self.assertRaises(SystemExit):
                build_qbl.main([command, "--help"])
            self.assertIn("--ledger", out.getvalue(), command)


class DeliverableTests(CommandCase):
    def test_new_intent_the_latest_clean_create_is_the_deliverable(self):
        self.create(self.args(), lambda *a, **k: _outcome("CREATED", "sol-1"))
        self.create(self.args(), lambda *a, **k: _outcome("CREATED", "sol-2"))
        by_solution = {e["solution_id"]: e["purpose"] for e in self.entries()}
        self.assertEqual(by_solution, {"sol-1": "attempt", "sol-2": "deliverable"})
        listed = cleanup_ledger.to_delete(cleanup_ledger.load(self.ledger))
        self.assertEqual([e["solution_id"] for e in listed], ["sol-1"])

    def test_edit_intent_nothing_is_a_deliverable_from_a_create(self):
        self.create(self.args(intent="edit"), lambda *a, **k: _outcome("CREATED", "sol-1"))
        self.assertEqual([e["purpose"] for e in self.entries()], ["validation-copy"])
        self.assertEqual(len(cleanup_ledger.to_delete(cleanup_ledger.load(self.ledger))), 1)

    def test_a_put_is_the_deliverable_only_when_it_succeeded(self):
        for outcome, purpose in ((qb_solutions.Outcome("UPDATED", http=200), "deliverable"),
                                 (qb_solutions.Outcome("REJECTED", http=400), "update")):
            entry = cleanup_ledger.record(
                self.ledger, purpose="update", app_name="A", source_sha256="a",
                sent_sha256="a", realm_host=HOST, outcome=outcome, call="PUT update")
            self.assertEqual(entry["purpose"], purpose)

    def _write_submission(self):
        submission = self.dir / "sub.yaml"
        with mock.patch.object(qb_auth, "stored_realm_host",
                               side_effect=qb_auth.AuthError("none")), mock.patch("sys.stdout"):
            build_qbl._create(self.args(write_submission=str(submission), realm=HOST,
                                        intent="edit"))
        return submission

    def _respond(self, submission, **kw):
        response = self.dir / "resp.json"
        response.write_text(json.dumps({
            "http_status": 200, "sha256": qb_common.sha256_text(submission.read_text()),
            "body": {"solutionId": "sol-r", "apps": ["bapp5"]}}))
        with mock.patch.object(qb_auth, "stored_realm_host",
                               side_effect=qb_auth.AuthError("none")), mock.patch("sys.stdout"):
            return build_qbl._create(self.args(platform_response=str(response),
                                               submission=str(submission), realm=HOST, **kw))

    def test_a_sidecar_cannot_set_the_purpose(self):
        submission = self._write_submission()
        sidecar = Path(str(submission) + ".json")
        meta = json.loads(sidecar.read_text())
        meta["purpose"] = "deliverable"
        sidecar.write_text(json.dumps(meta))
        self.assertEqual(self._respond(submission, intent="edit"), 0)
        entries = self.entries()
        self.assertEqual([e["purpose"] for e in entries], ["validation-copy"])
        self.assertEqual(len(entries), 1)   # the PENDING entry was finished, not duplicated

    def test_a_sidecar_realm_is_validated_again(self):
        submission = self._write_submission()
        sidecar = Path(str(submission) + ".json")
        meta = json.loads(sidecar.read_text())
        meta["realm_host"] = "evil.example/../x"
        sidecar.write_text(json.dumps(meta))
        with self.assertRaises(build_qbl.SkillInputError):
            self._respond(submission, intent="edit")
        self.assertEqual([e["outcome"] for e in self.entries()], ["PENDING"])


class UpdateFixture(unittest.TestCase):
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
        qb_update.write_deployed_record(self.deployed, solution_id="sol-1", realm_host=HOST,
                                        qbl_version="0.15")
        qb_update.write_build_record(self.document, deployed=self.deployed)

    def tearDown(self):
        self._t.cleanup()

    def create_entry(self, *, sent=None, host=HOST, when="2999-01-01T00:00:00+00:00",
                     relay=False, verified=False, sha=None):
        name = "Tracker (validation copy)"
        doc = qb_common.load_document(str(self.document))
        outcome = _outcome("CREATED")
        outcome.digest_verified = verified
        with mock.patch.object(cleanup_ledger, "utc_now", return_value=when):
            return cleanup_ledger.record(
                self.ledger, purpose="validation-copy", app_name=name,
                source_sha256=sha or self.sha,
                sent_sha256=sent or qb_common.sha256_text(qb_common.renamed_text(doc, name)),
                realm_host=host, outcome=outcome, intent="edit", relay=relay)

    def guards(self, host=HOST):
        return qb_update.check_guards(solution_id="sol-1", confirm="sol-1",
                                      document=self.document, ledger_path=self.ledger,
                                      realm_host=host)

class UnlockTests(UpdateFixture):
    def test_a_matching_create_unlocks(self):
        self.create_entry()
        self.assertEqual(self.guards().ledger_entry["id"], 1)

    def test_a_sent_text_that_is_not_the_source_with_a_new_name_does_not_unlock(self):
        self.create_entry(sent="0" * 64)
        with self.assertRaises(qb_update.UpdateRefused):
            self.guards()

    def test_a_create_in_another_realm_does_not_unlock(self):
        self.create_entry(host="myrealm.quickbase.com")
        with self.assertRaises(qb_update.UpdateRefused):
            self.guards()
        self.create_entry()
        with self.assertRaises(qb_update.UpdateRefused):
            self.guards(host="example.ui.quickbase.com")

    def test_a_create_older_than_the_deployed_export_does_not_unlock(self):
        self.create_entry(when="2000-01-01T00:00:00+00:00")
        with self.assertRaises(qb_update.UpdateRefused):
            self.guards()

    def test_a_relayed_create_unlocks_only_with_a_matching_digest(self):
        self.create_entry(relay=True, verified=False)
        with self.assertRaises(qb_update.UpdateRefused):
            self.guards()
        self.create_entry(relay=True, verified=True)
        self.assertEqual(self.guards().ledger_entry["id"], 2)

    def test_a_bare_solution_id_relay_is_ledgered_but_does_not_unlock(self):
        text = "x: 1\n"
        bare = qb_solutions.ingest_platform_response(
            {"solutionId": "sol-b", "apps": ["bapp9"]}, text)
        self.assertEqual(bare.outcome, "CREATED")
        self.assertFalse(bare.digest_verified)
        checked = qb_solutions.ingest_platform_response(
            {"solutionId": "sol-b", "sha256": qb_common.sha256_text(text)}, text)
        self.assertTrue(checked.digest_verified)
        entry = cleanup_ledger.record(
            self.ledger, purpose="validation-copy", app_name="x", source_sha256=self.sha,
            sent_sha256="z", realm_host=HOST, outcome=bare, intent="edit", relay=True)
        ledger = cleanup_ledger.load(self.ledger)
        self.assertIn(entry["id"], [e["id"] for e in cleanup_ledger.to_delete(ledger)])
        self.assertIsNone(cleanup_ledger.clean_create_for(ledger, self.sha))


class UpdateCommandTests(UpdateFixture):
    def setUp(self):
        super().setUp()
        self.create_entry()
        self.fresh = self.deployed.read_text()
        self.record_dry_run()

    def record_dry_run(self, **kw):
        values = dict(solution_id="sol-1", document_sha256=self.sha,
                      export_sha256=qb_common.sha256_text(self.fresh), realm_host=HOST)
        values.update(kw)
        return cleanup_ledger.record_dry_run(self.ledger, **values)

    def run_update(self, *, dry_run=False, fresh=None, confirm="sol-1", export=None):
        fresh = self.fresh if fresh is None else fresh
        args = _ns(solution_id="sol-1", document=str(self.document), confirm=confirm,
                   dry_run=dry_run, ledger=str(self.ledger), realm=None, timeout=5,
                   format="text")
        export = export or mock.Mock(return_value=(200, fresh, False))
        update = mock.Mock(return_value=qb_solutions.Outcome("UPDATED", http=200))
        out = io.StringIO()
        with mock.patch.object(qb_auth, "stored_realm_host", return_value=HOST), \
                mock.patch.object(qb_solutions, "export", export), \
                mock.patch.object(qb_solutions, "update", update), \
                mock.patch.object(qb_solutions, "create") as create, \
                mock.patch("sys.stdout", out), mock.patch("sys.stderr", io.StringIO()):
            code = build_qbl._update(args)
        return code, export, update, create, out.getvalue()

    def test_the_deployed_solution_is_refetched_and_the_preview_comes_from_it(self):
        code, export, update, _, out = self.run_update()
        self.assertEqual(code, 0)
        export.assert_called_once()
        update.assert_called_once()
        self.assertIn("Notes", out)
        entries = cleanup_ledger.load(self.ledger)["entries"]
        self.assertEqual((entries[-1]["call"], entries[-1]["outcome"], entries[-1]["purpose"]),
                         ("PUT update", "UPDATED", "deliverable"))

    def test_a_changed_deployed_solution_refuses_before_the_put(self):
        code, _, update, _, _ = self.run_update(fresh=self.fresh + "\n# changed on the server\n")
        self.assertNotEqual(code, 0)
        update.assert_not_called()
        self.assertFalse([e for e in cleanup_ledger.load(self.ledger)["entries"]
                          if e.get("call") == "PUT update"])

    def test_the_changed_deployed_refusal_names_a_refetch_that_overwrites(self):
        # `fetch-deployed` refuses to replace an existing export without --force,
        # so advice without it is a command that does nothing.
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            args = _ns(solution_id="sol-1", document=str(self.document), confirm="sol-1",
                       dry_run=True, ledger=str(self.ledger), realm=None, timeout=5,
                       format="text")
            with mock.patch.object(qb_auth, "stored_realm_host", return_value=HOST), \
                    mock.patch.object(qb_solutions, "export",
                                      mock.Mock(return_value=(200, self.fresh + "#x\n", False))):
                build_qbl._update(args)
        self.assertIn("fetch-deployed sol-1 --out current.qbl.yaml --force", err.getvalue())

    def test_a_failed_refetch_refuses(self):
        code, _, update, _, _ = self.run_update(export=mock.Mock(return_value=(500, "", False)))
        self.assertNotEqual(code, 0)
        update.assert_not_called()

    def test_the_put_has_a_pending_entry_while_it_is_sent(self):
        seen = []

        def put(*a, **k):
            seen.append([(e["call"], e["outcome"]) for e in
                         cleanup_ledger.load(self.ledger)["entries"]])
            return qb_solutions.Outcome("UPDATED", http=204)

        with mock.patch.object(qb_solutions, "update", side_effect=put), \
                mock.patch.object(qb_auth, "stored_realm_host", return_value=HOST), \
                mock.patch.object(qb_solutions, "export",
                                  return_value=(200, self.fresh, False)), \
                mock.patch("sys.stdout"):
            code = build_qbl._update(_ns(
                solution_id="sol-1", document=str(self.document), confirm="sol-1",
                dry_run=False, ledger=str(self.ledger), realm=None, timeout=5, format="text"))
        self.assertEqual(code, 0)
        self.assertIn(("PUT update", "PENDING"), seen[0])

    def test_a_corrupt_ledger_refuses_the_update_before_any_request(self):
        self.ledger.write_text("nope")
        with self.assertRaises(build_qbl.SkillInputError):
            self.run_update()
        # nothing was fetched or sent
        export = mock.Mock(return_value=(200, self.fresh, False))
        with self.assertRaises(build_qbl.SkillInputError):
            self.run_update(export=export)
        export.assert_not_called()

    def test_dry_run_prints_the_preview_and_guards_and_sends_nothing(self):
        code, export, update, create, out = self.run_update(dry_run=True, confirm=None)
        self.assertEqual(code, 0)
        update.assert_not_called()
        create.assert_not_called()
        self.assertIn("DRY RUN", out)
        self.assertIn("GUARDS", out)
        self.assertIn("DELETION PREVIEW", out)
        self.assertIn("Notes", out)
        entries = cleanup_ledger.load(self.ledger)["entries"]
        self.assertEqual([e["call"] for e in entries], ["POST create"])

    def test_update_needs_a_recent_matching_dry_run_recorded_in_the_ledger(self):
        def fresh_ledger():
            data = cleanup_ledger.load(self.ledger)
            data["dry_runs"] = []
            cleanup_ledger.save(self.ledger, data)

        fresh_ledger()
        code, _, update, _, _ = self.run_update()
        self.assertNotEqual(code, 0)
        update.assert_not_called()
        # a completed dry run records one, and then the update goes ahead
        code, _, _, _, _ = self.run_update(dry_run=True, confirm=None)
        self.assertEqual(code, 0)
        self.assertEqual(len(cleanup_ledger.load(self.ledger)["dry_runs"]), 1)
        code, _, update, _, _ = self.run_update()
        self.assertEqual(code, 0)
        update.assert_called_once()

    def test_a_dry_run_for_another_document_solution_export_or_time_does_not_count(self):
        for kw in (dict(document_sha256="0" * 64), dict(solution_id="sol-2"),
                   dict(export_sha256="1" * 64), dict(realm_host="myrealm.quickbase.com")):
            data = cleanup_ledger.load(self.ledger)
            data["dry_runs"] = []
            cleanup_ledger.save(self.ledger, data)
            self.record_dry_run(**kw)
            code, _, update, _, _ = self.run_update()
            self.assertNotEqual(code, 0, kw)
            update.assert_not_called()
        data = cleanup_ledger.load(self.ledger)
        data["dry_runs"] = []
        cleanup_ledger.save(self.ledger, data)
        item = self.record_dry_run()
        data = cleanup_ledger.load(self.ledger)
        data["dry_runs"][0]["time"] = "2000-01-01T00:00:00+00:00"
        cleanup_ledger.save(self.ledger, data)
        code, _, update, _, _ = self.run_update()
        self.assertNotEqual(code, 0)
        update.assert_not_called()

    def test_dry_run_reports_a_guard_failure_without_sending(self):
        self.document.write_text(self.document.read_text() + "\n# edited\n")
        code, _, update, _, _ = self.run_update(dry_run=True, confirm=None)
        self.assertNotEqual(code, 0)
        update.assert_not_called()

    def test_a_bad_solution_id_is_refused_before_anything(self):
        args = _ns(solution_id="../x", document=str(self.document), confirm="../x",
                   dry_run=False, ledger=str(self.ledger), realm=None, timeout=5,
                   format="text")
        with mock.patch.object(qb_solutions, "export") as export:
            with self.assertRaises(build_qbl.SkillInputError):
                build_qbl._update(args)
        export.assert_not_called()


class _Trickle:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, size=-1):
        time.sleep(0.2)
        return b"x"


class ClientLimitTests(unittest.TestCase):
    def call(self, side_effect, **kw):
        fake = FakeKeystore(secret="s3", realm=HOST)
        with patched_keystore(fake), mock.patch(OPEN, side_effect=side_effect) as opened:
            outcome = qb_solutions.create("Version: 0.15\n", realm_host=HOST,
                                          timeout=kw.get("timeout", 5))
        return outcome, opened

    def test_the_timeout_bounds_a_slow_trickling_body(self):
        started = time.monotonic()
        outcome, _ = self.call(lambda request, timeout: _Trickle(), timeout=1)
        self.assertEqual(outcome.outcome, qb_solutions.TIMEOUT)
        self.assertLess(time.monotonic() - started, 3)

    def test_a_worker_that_never_returns_is_a_timeout_too(self):
        release = threading.Event()
        self.addCleanup(release.set)

        def hang(request, timeout):
            release.wait(10)
            return FakeResponse(200, "{}")

        started = time.monotonic()
        outcome, _ = self.call(hang, timeout=1)
        self.assertEqual(outcome.outcome, qb_solutions.TIMEOUT)
        self.assertLess(time.monotonic() - started, 3)

    def test_solution_ids_are_validated_before_a_url_is_built(self):
        for bad in ("../x", "a b", "", "x" * 65, "a/b", "a?b=1", "a#b", "ü", "a\n", None):
            with self.assertRaises(build_qbl.SkillInputError, msg=repr(bad)):
                qb_solutions.solution_url(bad)
        with mock.patch(OPEN) as opened:
            for call in (lambda: qb_solutions.export("../x", realm_host=HOST, qbl_version="0.15"),
                         lambda: qb_solutions.update("a/b", "x", realm_host=HOST,
                                                     qbl_version="0.15")):
                with self.assertRaises(build_qbl.SkillInputError):
                    call()
        opened.assert_not_called()
        uuid = "123e4567-e89b-12d3-a456-426614174000"
        self.assertEqual(qb_solutions.solution_url(uuid), f"{qb_solutions.API_BASE}/{uuid}")
        self.assertEqual(qb_solutions.solution_url("my_alias-1"),
                         f"{qb_solutions.API_BASE}/my_alias-1")

    def test_the_opener_refuses_redirects_so_the_token_never_follows_one(self):
        handlers = qb_solutions._opener().handlers
        self.assertTrue(any(isinstance(h, qb_solutions._NoRedirect) for h in handlers))
        with self.assertRaises(qb_solutions.RedirectRefused):
            qb_solutions._NoRedirect().redirect_request(
                mock.Mock(), None, 302, "Found", {}, "https://elsewhere.example/")

    def test_a_redirect_is_an_error_outcome(self):
        def refused(request, timeout):
            raise qb_solutions.RedirectRefused("HTTP 302: the server redirected")

        outcome, _ = self.call(refused)
        self.assertEqual(outcome.outcome, qb_solutions.ERROR)
        self.assertIn("redirect", outcome.detail)
        bare = qb_solutions.parse_response(302, "")
        self.assertEqual(bare.outcome, qb_solutions.ERROR)

    def test_an_empty_2xx_put_is_success_and_an_empty_create_is_not(self):
        for status in (200, 204):
            outcome = qb_solutions.parse_response(
                status, "", expect_solution_id=False, success_outcome=qb_solutions.UPDATED)
            self.assertEqual(outcome.outcome, qb_solutions.UPDATED)
        fake = FakeKeystore(secret="s3", realm=HOST)
        with patched_keystore(fake), mock.patch(
                OPEN, side_effect=lambda r, timeout: FakeResponse(204, "")):
            put = qb_solutions.update("sol-1", "x", realm_host=HOST, qbl_version="0.15")
        self.assertEqual(put.outcome, qb_solutions.UPDATED)
        self.assertEqual(qb_solutions.parse_response(200, "").outcome, qb_solutions.ERROR)

    def test_an_http_error_response_is_closed(self):
        body = io.BytesIO(json.dumps({"errors": ["bad"]}).encode())

        def refuse(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 400, "bad", {}, body)

        outcome, _ = self.call(refuse)
        self.assertEqual(outcome.outcome, qb_solutions.REJECTED)
        self.assertTrue(body.closed)


class RealmAndWordingTests(unittest.TestCase):
    def test_a_realm_is_matched_whole_with_no_whitespace_or_controls(self):
        for bad in ("example.quickbase.com\n", " a", "a ", "a b", "a\tb", "a\x00", "a\x1b[0m",
                    "a b", "a\r"):
            with self.assertRaises(qb_auth.AuthError, msg=repr(bad)):
                qb_auth.normalize_realm(bad)
        self.assertEqual(qb_auth.normalize_realm("demo").host, "demo.quickbase.com")

    def test_links_are_built_only_on_validated_hosts(self):
        with self.assertRaises(qb_auth.AuthError):
            cleanup_ledger.app_link("evil.example/path?x=", "bapp1")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        entry = cleanup_ledger.record(
            Path(tmp.name) / "l.json", purpose="probe", app_name="A", source_sha256="a",
            sent_sha256="b", realm_host="evil.example/x", outcome=_outcome("CREATED"))
        self.assertEqual(entry["links"], [])

    def test_the_docs_describe_the_stdin_store_on_macos(self):
        for path in (SKILL_DIR / "scripts" / "store_token.py",
                     SKILL_DIR / "scripts" / "qb_auth.py",
                     SKILL_DIR / "SKILL.md", SKILL_DIR / "README.md"):
            text = path.read_text()
            self.assertIn("security -i", text, path.name)
            self.assertNotIn("-w <secret>", text, path.name)

    def test_skill_md_wording_and_workflow(self):
        text = (SKILL_DIR / "SKILL.md").read_text()
        self.assertIn("api.quickbase.com", text)
        self.assertIn("--dry-run", text)
        self.assertLess(text.index("--dry-run"), text.index("update <solutionId> app.qbl.yaml --confirm"))
        self.assertIn("current working directory", text)
        for name in ("SKILL.md", "README.md"):
            body = (SKILL_DIR / name).read_text()
            self.assertIn("cannot verify that a person approved", body, name)
            self.assertIn("command-permission prompt", body, name)
        self.assertIn("NOT that approval", text)


    def test_the_credential_code_reads_no_environment_and_no_file(self):
        source = (SKILL_DIR / "scripts" / "qb_auth.py").read_text(encoding="utf-8")
        code = "\n".join(line for line in source.splitlines()
                         if not line.lstrip().startswith("#"))
        for needle in ("os.environ", "getenv", "open(", "read_text", "sys.stdin", "import os"):
            self.assertNotIn(needle, code.split('"""', 2)[-1], needle)


if __name__ == "__main__":
    unittest.main()

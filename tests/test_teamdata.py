"""Run with: python -m unittest discover tests"""
import argparse
import datetime as dt
import http.server
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import teamdata  # noqa: E402

NOW = dt.datetime(2026, 11, 11, 12, 0, tzinfo=dt.timezone.utc)  # a Wednesday


def ago(days):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat(timespec="seconds")


def git(repo, *args, date=None, name="Ada Obi", email="ada@acme.io"):
    env = {**os.environ, "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_NAME": name,
           "GIT_COMMITTER_EMAIL": email}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, env=env)


def commit(repo, subject, date, **who):
    git(repo, "commit", "--allow-empty", "-m", subject, date=date, **who)


def options(repo, **over):
    base = dict(days=2, since=None, stall_days=3, person=None, team=None, no_github=True, max_items=40, repo=[repo])
    return argparse.Namespace(**{**base, **over})


def build(args):
    return teamdata.build(args, dt.datetime.now(dt.timezone.utc))


class Window(unittest.TestCase):
    def test_monday_covers_the_weekend(self):
        monday = dt.datetime(2026, 11, 9, 9, tzinfo=dt.timezone.utc)
        start, _ = teamdata.window(None, None, monday)
        self.assertEqual((monday - start).days, 3)

    def test_midweek_is_one_day(self):
        start, _ = teamdata.window(None, None, NOW)
        self.assertEqual((NOW - start).days, 1)


class Git(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        git(self.repo, "init", "-q")

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_commits_in_the_window_only(self):
        commit(self.repo, "old work", ago(20))
        commit(self.repo, "add billing page", ago(1))
        out = build(options(self.repo))
        subjects = [c["subject"] for c in out["people"]["Ada Obi"]["commits"]]
        self.assertEqual(subjects, ["add billing page"])

    def test_bots_are_left_out(self):
        commit(self.repo, "bump lodash", ago(1), name="dependabot[bot]", email="bot@github.com")
        self.assertEqual(build(options(self.repo))["people"], {})

    def test_a_github_noreply_email_folds_into_the_login(self):
        people = teamdata.People()
        first = people.name("Ada Obi", "123+adaobi@users.noreply.github.com")
        self.assertEqual(people.name("adaobi"), first)

    def test_a_login_folds_into_a_matching_git_name(self):
        people = teamdata.People()
        self.assertEqual(people.name("William Martin"), people.name("williammartin"))

    def test_team_file_joins_identities(self):
        commit(self.repo, "one", ago(1), name="ada", email="a@x.io")
        commit(self.repo, "two", ago(1), name="Ada O", email="b@x.io")
        team = pathlib.Path(self.repo) / "team-map.json"
        team.write_text(json.dumps({"Ada Obi": ["a@x.io", "b@x.io"]}), encoding="utf-8")
        out = build(options(self.repo, team=str(team)))
        self.assertEqual(list(out["people"]), ["Ada Obi"])
        self.assertEqual(len(out["people"]["Ada Obi"]["commits"]), 2)

    def test_not_a_repo_is_reported_not_hidden(self):
        with tempfile.TemporaryDirectory() as empty:
            out = build(options(empty))
        self.assertEqual(out["sources"]["git"]["status"], "unavailable")

    def test_linear_without_a_key_says_so(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("LINEAR_API_KEY", None)
            out = build(options(self.repo))
        self.assertEqual(out["sources"]["linear"]["status"], "not_configured")
        self.assertIn("LINEAR_API_KEY", out["sources"]["linear"]["reason"])

    def test_people_are_in_alphabetical_order(self):
        commit(self.repo, "a", ago(1), name="zed", email="z@x.io")
        commit(self.repo, "b", ago(1), name="Amy", email="a@x.io")
        self.assertEqual(list(build(options(self.repo))["people"]), ["Amy", "zed"])

    def test_person_filter(self):
        commit(self.repo, "a", ago(1))
        commit(self.repo, "b", ago(1), name="Bo Li", email="bo@acme.io")
        self.assertEqual(list(build(options(self.repo, person="bo"))["people"]), ["Bo Li"])


def pr(number, **over):
    base = dict(number=number, title=f"PR {number}", url=f"https://gh/{number}", author={"login": "adaobi", "name": "Ada Obi"},
                state="OPEN", isDraft=False, createdAt=ago(10), updatedAt=ago(1), mergedAt=None, reviewDecision="",
                reviews=[], reviewRequests=[], headRefName=f"branch-{number}")
    return {**base, **over}


class GitHub(unittest.TestCase):
    def fake_run(self, prs, closed=()):
        real = teamdata.run

        def run(cmd, cwd=None):
            if cmd[0] != "gh":
                return real(cmd, cwd)
            if cmd[1:3] == ["repo", "view"]:
                return 0, json.dumps({"nameWithOwner": "acme/app"}), ""
            if cmd[1:3] == ["pr", "list"]:
                return 0, json.dumps(prs), ""
            return 0, json.dumps(list(closed)), ""
        return run

    def collect(self, prs, closed=()):
        with tempfile.TemporaryDirectory() as repo:
            git(repo, "init", "-q")
            with mock.patch.object(teamdata, "run", self.fake_run(prs, closed)), \
                    mock.patch.object(teamdata.shutil, "which", return_value="gh"), \
                    mock.patch.dict(os.environ):
                os.environ.pop("LINEAR_API_KEY", None)
                return build(options(repo, no_github=False))

    def kinds(self, out):
        return {s["number"]: s["kind"] for s in out["stalled"]}

    def test_no_review(self):
        self.assertEqual(self.kinds(self.collect([pr(1)]))[1], "waiting_for_review")

    def test_changes_requested_and_idle(self):
        out = self.collect([pr(2, reviewDecision="CHANGES_REQUESTED", updatedAt=ago(5),
                               reviews=[{"author": {"login": "bo"}, "submittedAt": ago(5)}])])
        self.assertEqual(self.kinds(out)[2], "changes_requested_idle")

    def test_reviewed_and_idle(self):
        out = self.collect([pr(3, updatedAt=ago(6), reviews=[{"author": {"login": "bo"}, "submittedAt": ago(6)}])])
        self.assertEqual(self.kinds(out)[3], "pr_idle")

    def test_drafts_never_count_as_stalled(self):
        self.assertEqual(self.collect([pr(4, isDraft=True)])["stalled"], [])

    def test_fresh_pr_is_not_stalled(self):
        self.assertEqual(self.collect([pr(5, createdAt=ago(1))])["stalled"], [])

    def test_merged_and_reviews_land_on_the_right_people(self):
        out = self.collect([pr(6, state="MERGED", mergedAt=ago(1), createdAt=ago(1),
                               reviews=[{"author": {"login": "bo"}, "submittedAt": ago(1)}])])
        self.assertEqual(out["people"]["Ada Obi"]["prs_merged"][0]["number"], 6)
        self.assertEqual(out["people"]["bo"]["prs_reviewed"][0]["number"], 6)

    def test_self_review_is_not_counted(self):
        out = self.collect([pr(7, createdAt=ago(1), reviews=[{"author": {"login": "adaobi"}, "submittedAt": ago(1)}])])
        self.assertEqual(out["people"]["Ada Obi"]["prs_reviewed"], [])

    def test_a_reviewer_folds_into_their_name_even_when_seen_first(self):
        out = self.collect([pr(8, createdAt=ago(1), reviews=[{"author": {"login": "bo"}, "submittedAt": ago(1)}]),
                            pr(9, createdAt=ago(1), author={"login": "bo", "name": "Bo Li"})])
        self.assertEqual(out["people"]["Bo Li"]["prs_reviewed"][0]["number"], 8)
        self.assertNotIn("bo", out["people"])

    def test_review_bots_are_left_out(self):
        out = self.collect([pr(10, createdAt=ago(1), reviews=[
            {"author": {"login": "copilot-pull-request-reviewer"}, "submittedAt": ago(1)}])])
        self.assertNotIn("copilot-pull-request-reviewer", out["people"])

    def test_old_news_sorts_after_recent_slips(self):
        out = self.collect([pr(11, createdAt=ago(400)), pr(12, createdAt=ago(5))])
        self.assertEqual([(s["number"], s["abandoned"]) for s in out["stalled"]], [(12, False), (11, True)])

    def test_a_closed_unmerged_pr_is_not_reported_as_opened(self):
        out = self.collect([pr(13, state="CLOSED", createdAt=ago(1)), pr(14, createdAt=ago(1))])
        self.assertEqual([p["number"] for p in out["people"]["Ada Obi"]["prs_opened"]], [14])

    def test_waiting_on_uses_the_same_name_as_people(self):
        out = self.collect([pr(15, createdAt=ago(5), reviewRequests=[{"login": "bo"}]),
                            pr(16, createdAt=ago(1), author={"login": "bo", "name": "Bo Li"})])
        self.assertEqual(out["stalled"][0]["waiting_on"], ["Bo Li"])

    def test_a_completed_issue_is_credited_to_its_assignee(self):
        closed = [{"number": 1, "title": "t", "url": "u", "stateReason": "COMPLETED", "assignees": [{"login": "bo"}]}]
        self.assertEqual(self.collect([], closed)["people"]["bo"]["issues_completed"][0]["number"], 1)

    def test_an_unassigned_or_not_planned_issue_credits_nobody(self):
        closed = [{"number": 1, "title": "t", "url": "u", "stateReason": "COMPLETED", "assignees": []},
                  {"number": 2, "title": "t", "url": "u", "stateReason": "NOT_PLANNED", "assignees": [{"login": "bo"}]}]
        self.assertEqual(self.collect([], closed)["people"], {})

    def test_github_apps_are_left_out(self):
        closed = [{"number": 1, "title": "t", "url": "u", "stateReason": "COMPLETED", "assignees": [{"login": "app/triage"}]}]
        self.assertEqual(self.collect([], closed)["people"], {})

    def test_gh_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as repo:
            git(repo, "init", "-q")
            real = teamdata.run

            def run(cmd, cwd=None):
                return (1, "", "not logged in") if cmd[0] == "gh" else real(cmd, cwd)
            with mock.patch.object(teamdata, "run", run), mock.patch.object(teamdata.shutil, "which", return_value="gh"):
                out = build(options(repo, no_github=False))
        self.assertEqual(out["sources"]["github"]["status"], "unavailable")
        self.assertIn("not logged in", out["sources"]["github"]["reason"])


def ticket(identifier, kind, **over):
    base = dict(identifier=identifier, title=f"Ticket {identifier}", url=f"https://linear/{identifier}", updatedAt=ago(1),
                startedAt=ago(5), completedAt=None, branchName="", state={"name": "In Progress", "type": kind},
                assignee={"name": "Ada Obi", "displayName": "ada"}, attachments={"nodes": []})
    return {**base, **over}


class Linear(unittest.TestCase):
    """Runs the real HTTP code against a local stand-in for the Linear API."""

    def serve(self, recent, started):
        calls = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                calls.append((self.headers["Authorization"], body))
                nodes = started if "state" in body["variables"]["filter"] else recent
                payload = json.dumps({"data": {"issues": {"nodes": nodes}}}).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *a):
                pass
        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}/graphql", calls

    def collect(self, recent, started=(), subjects=()):
        url, calls = self.serve(list(recent), list(started))
        with tempfile.TemporaryDirectory() as repo:
            git(repo, "init", "-q")
            for s in subjects:
                commit(repo, s, ago(1))
            with mock.patch.dict(os.environ, {"LINEAR_API_KEY": "test-key", "LINEAR_API_URL": url}):
                return build(options(repo)), calls

    def done(self, identifier):
        return ticket(identifier, "completed", completedAt=ago(1), state={"name": "Done", "type": "completed"})

    def test_sends_the_key_without_bearer(self):
        _, calls = self.collect([])
        self.assertEqual(calls[0][0], "test-key")

    def test_idle_ticket(self):
        out, _ = self.collect([], [ticket("ENG-1", "started", updatedAt=ago(6))])
        self.assertEqual(out["stalled"][0]["kind"], "ticket_idle")
        self.assertEqual(out["stalled"][0]["days_idle"], 6)

    def test_done_without_code_needs_a_team_that_links_tickets(self):
        out, _ = self.collect([self.done("ENG-1"), self.done("ENG-2")], subjects=["ENG-1 fix login"])
        self.assertEqual([s["id"] for s in out["stalled"] if s["kind"] == "done_without_code"], ["ENG-2"])

    def test_done_check_skipped_when_nothing_links(self):
        out, _ = self.collect([self.done("ENG-1")], subjects=["fix login"])
        self.assertEqual(out["stalled"], [])
        self.assertIn("skipped", out["sources"]["linear"]["done_check"])

    def test_tickets_land_on_people(self):
        out, _ = self.collect([self.done("ENG-1")], [ticket("ENG-2", "started")])
        self.assertEqual(out["people"]["Ada Obi"]["tickets_done"][0]["id"], "ENG-1")
        self.assertEqual(out["people"]["Ada Obi"]["tickets_in_progress"][0]["id"], "ENG-2")


class Pack(unittest.TestCase):
    skills = sorted(p for p in (ROOT / "skills").iterdir() if (p / "SKILL.md").exists())

    def test_five_skills(self):
        self.assertEqual([p.name for p in self.skills],
                         ["1on1-prep", "investor-update", "standup", "weekly-update", "what-slipped"])

    def test_every_copy_of_the_script_matches(self):
        source = (ROOT / "tools" / "teamdata.py").read_bytes()
        for skill in self.skills:
            self.assertEqual((skill / "teamdata.py").read_bytes(), source, skill.name)

    def test_frontmatter(self):
        for skill in self.skills:
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertRegex(text, rf"\A---\nname: {re.escape(skill.name)}\ndescription: >-\n")

    def test_house_wording(self):
        files = [ROOT / "README.md", *(s / "SKILL.md" for s in self.skills)]
        for path in files:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("—", text, path.name)
            self.assertNotRegex(text, r"(?i)\bship(ped|ping|s)?\b", path.name)


if __name__ == "__main__":
    unittest.main()

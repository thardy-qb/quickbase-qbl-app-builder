# Contributing to the Quickbase QBL App Builder

Issues and pull requests are welcome. The maintainer reviews every change, and
only the maintainer merges to `main` or publishes a release.

## Reporting a problem

Open an issue with:

- the Skill version (the `VERSION` file);
- what you asked Claude to do, and what happened instead;
- the smallest piece of QBL that shows it, with names changed (see Privacy).

For a security problem, do not open an issue. See [SECURITY.md](SECURITY.md).

## Proposing a change

1. Fork the repository and branch from `main`.
2. Keep each pull request to one change, and say in the description why it is
   needed. A failing case, as a document or a test, is the most useful thing you
   can include.
3. Add or update a test under `tests/` for anything that changes behaviour.
4. Run the tests with Python 3.9 or later:

       python3 -m unittest discover -s tests

5. Open the pull request against `main`.

## How changes are released

This repository is the published form of each release, so `main` only changes
when a version is released. A change you propose is reviewed here. If it is
accepted, the maintainer brings it into the next release, and the pull request
is closed with a link to the release that carries it, rather than merged
directly. Your contribution is credited in that release's notes.

Changes that may take longer to review, or be declined:

- changes to the files under `scripts/qblparser/` that are only formatting or
  comments, which are not kept between releases;
- new third-party dependencies (the Skill runs on the standard library plus the
  packages bundled under `scripts/vendor/`);
- anything that sends data anywhere other than the Quickbase realm the user
  chose.

## Privacy

Your QBL document, requirements and cleanup ledger can describe a real application and name apps in your realm. Never attach them in full to an issue or pull request. Cut a document down to the few lines that show the problem, and rename tables, fields and values. Never paste a user token anywhere; if one was exposed, rotate it in Quickbase.

## Licence

By contributing, you agree that your contribution is licensed under the
[MIT License](LICENSE) that covers this repository.

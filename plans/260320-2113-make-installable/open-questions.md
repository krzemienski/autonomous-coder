# Open Questions

## make-installable - 2026-03-20

- [ ] **License field in pyproject.toml** -- The plan specifies `license = "MIT"` but there is no LICENSE file in the repo. Should we add one, use a different license, or omit the field? — Affects PyPI publishability.
- [ ] **claude-agent-sdk version floor** -- Plan uses `>=0.1.0` but the SDK is at 0.1.50 and pre-1.0 APIs change frequently. Should we pin more tightly (e.g., `>=0.1.40`) to avoid broken installs with older versions? — Affects install reliability for new users.
- [ ] **textual version floor** -- Plan uses `>=0.40.0`. The `CSS_PATH` class attribute pattern and other Textual APIs may have a more recent minimum. Should we verify against textual's changelog? — Affects install reliability.
- [ ] **README update scope** -- The README currently says `python -m autonomous_coder` without installation instructions. Should the executor also update README with install instructions, or is that a separate task? — Affects first-run experience.
- [ ] **`commands/` directory** -- Contains only `autonomous-code.md`. Is this directory still needed or can it be cleaned up? — Affects repo cleanliness.

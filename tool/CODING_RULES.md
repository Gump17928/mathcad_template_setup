# Coding rules for this project

Written for the next person to change this code, whether they are new to programming or very experienced.
Each rule says what to do, why, and where you can see it applied here. `ruff` (config in `pyproject.toml`) enforces
the mechanical ones; run `run_tests.bat` before and after every change.

## 1. One job per function and per module
A function should be describable in one sentence without the word "and". Keep functions to about 40 lines,
7 parameters and 10 branches (ruff checks this). If you need a comment to mark a "phase" inside a function, that phase
is a function.
*Here:* `load_discipline` was one 136-line function; it is now `_assign_names`, `_classify_row`, `_live_formula`,
`_numeric_row` and `_build_summary`. `mcdx_build.py` (worksheet XML), `rich_text.py` (text), `opc.py` (zip packaging)
and `formula.py` (arithmetic) each own one subject.

## 2. No magic numbers or strings
A bare `33.6` or `"calc"` tells the reader nothing. Give it a name at the top of the file with its unit and, if it is not
obvious, why it has that value.
*Here:* page geometry in `mcdx_build.py`, row layout in `build_template.py`, text metrics in `rich_text.py`.

## 3. Say each fact once
If two places must agree (how tall a row is, how a key is derived), make one the source and call it from the other.
Copies drift apart.
*Here:* `row_extent` is used both to place a row and to decide where a page ends; `default_key` is used by the wizard and
the builder; `prime_com` holds the one copy of "open, wait, close, quit".

## 4. Make data explicit
Use a `dataclass` or `Enum` instead of a tuple, a loose dict or a string that stands for a choice. Then typos fail
immediately and the fields document themselves.
*Here:* `RowKind`, `IoKind`, `Row`, `Discipline`, `Box`, and the formula tree (`Num`, `Var`, `BinOp`, ...) instead of
`("mult", a, b)` tuples.

## 5. Keep decisions separate from side effects
Code that works things out (parsing, layout, classification) should not also touch files, the screen or Prime. Do the
thinking in pure functions and let a thin outer layer do the I/O. Pure code is easy to test.
*Here:* `csv_import` and `formula` do no I/O besides reading the CSV; only `Sheet.save`, `build_project` and the
Prime scripts write or drive anything.

## 6. Dependencies point one way
Lower layers must not import higher ones. Order here: `formula`, `opc` -> `rich_text` -> `mcdx_build` -> `csv_import`
-> `build_template` (and `prime_com` -> the Prime scripts). If you need to import "upwards", the code belongs lower.

## 7. Fail early, loudly and usefully
Check input where it enters (the CSV, `project.json`) and raise an error that says what is wrong and where
("line 6: 'section' and 'label' must both be filled in"). Catch the specific exception you expect, never a bare
`except:`. Never let a failure pass silently, but do not crash on something the user can fix: report it and carry on
when that is safe (see the warnings in `import_report.txt`).

## 8. Comments explain why; names and docstrings explain what
Don't restate the code. Do write down what the code cannot say: a Prime quirk, a measured number, a decision.
Every module and every non-trivial public function gets a docstring. Delete dead code instead of commenting it out.
*Here:* "Prime refuses to open a worksheet with an include unless the package also holds a cached copy" sits next to
`Sheet.include`.

## 9. Prefer separate functions to mode flags
A function whose behaviour changes shape depending on a flag or on which optional arguments are given is really two
functions. Split it so each does one thing.
*Here:* the old `Sheet.text(..., into=, top=, hf=)` is now `text`, `text_at`, `header_text` and `footer_text`.

## 10. Clean up after yourself
Anything you open, start or lock must be released even when something fails. Use `with` blocks and context managers.
*Here:* `prime_session()` always quits Prime, and only closes the worksheets it opened itself.

## 11. Never change what you cannot check
Before restructuring code, put a test around its current behaviour. Then change one thing at a time and run the tests
after each. A refactor must produce identical output.
*Here:* `tests/test_build.py` rebuilds the Example project and compares all 288 package parts with a stored snapshot
(`tests/golden_example.json`). If you change output on purpose, review the difference, then refresh it with
`python tests/test_build.py --update`.

## 12. Leave it a little simpler than you found it
When you find an unused function, parameter or file, remove it. Don't add options "in case" - add them when they are
needed. Every extra option is more code to read, test and get wrong.

## Quick checklist before you finish a change
- [ ] `run_tests.bat` passes (tests and lint).
- [ ] New behaviour has a test; a bug fix has a test that failed before the fix.
- [ ] No new magic numbers, no function over about 40 lines, no copy-pasted blocks.
- [ ] Docstring on anything new that is public; a *why* comment next to anything surprising.
- [ ] If the worksheet XML changed: rebuilt Example and opened it in Prime (`check_in_prime.bat`).
- [ ] README / `tool\DEVELOPER_NOTES.md` updated if behaviour or layout changed.

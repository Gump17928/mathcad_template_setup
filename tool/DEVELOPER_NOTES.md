# Developer notes

Read `CODING_RULES.md` first. Run `run_tests.bat` before and after every change.

## Layout

| File | Role |
|---|---|
| `build_template.py` | Driver: reads `project.json`, loads the CSVs, lays out and saves the worksheets and the master. |
| `project_config.py` | `project.json` as typed objects (`ProjectConfig`, `Discipline`), validated; `csv` is optional per discipline. |
| `page_parts.py` | Header/footer, title block and the link-target tags shared by every generated sheet. |
| `blank_template.py` | Disciplines without a CSV: the blank template, the never-overwrite rule, the master's lines from designated outputs, variable-name clash check. |
| `csv_import.py` | CSV to model: variable names, live-formula detection, unit checking, summary selection. |
| `formula.py` | Plain-arithmetic formulas: parse, variables, evaluate, print. No Mathcad knowledge. |
| `mcdx_build.py` | Writes the worksheet XML (regions, areas, includes, designations); `Sheet` and `Frame`. |
| `rich_text.py` | Styled text with links, XAML packages, text-height estimate. |
| `opc.py` | Generic zip-package and relationship helpers. No Mathcad knowledge. |
| `mcdx_results.py` | Reads calculated results and designated outputs (variable, alias, unit setting) out of a Prime-saved package. |
| `prime_com.py` | Drives Prime over COM (`MathcadPrime.Application`, pywin32); always cleans up. |
| `verify_in_prime.py`, `export_pdf.py` | Command-line scripts built on `prime_com`. |
| `project_io.py` | Finding the project folder; naming defaults shared by the wizard and the builder. |
| `new_project.py` | The wizard behind `new_project.bat`. |
| `skeleton/skeleton.mcdx` | The settings and document-property parts copied into every generated worksheet. Taken from a Prime 12.0.1.0 worksheet, reduced to the six parts the generator reads, with neutral author properties. |
| `reference/` | Local only (git-ignored): the probe worksheet the XML shapes were taken from, and PTC's sample worksheet. Not published because they carry personal metadata and third-party content. If you need to learn a new XML shape, save a small worksheet from Prime that uses the feature and unzip it. |

Dependency order: `formula`, `opc` -> `rich_text` -> `mcdx_build` -> `csv_import`, `project_config` -> `page_parts` -> `blank_template` -> `build_template`.

## Tests

`run_tests.bat` (or `python -m unittest discover -s tests`) runs everything; it takes about a second.

- `tests/test_build.py` - rebuilds `projects/Example` and compares every package part with `tests/golden_example.json`
  (random ids and timestamps blanked out), plus CSV import tests.
- `tests/test_formula.py` - the formula parser and evaluator.
- `tests/test_workflow.py` - wizard helpers; a freshly created project must build; blank (CSV-less) disciplines are
  created, never overwritten, read for designated outputs and summarised by the master.

If a change *should* alter the output, look at what changed, open the result in Prime
(`check_in_prime.bat`), then refresh the snapshot with `python tests/test_build.py --update`.
These tests do not need Prime. Whether Prime accepts the files is checked by `check_in_prime.bat`.

## How features are stored (observed in Prime 12.0.1.0)

| Feature | Stored as |
|---|---|
| Heading | `<Run style="Heading 1">` in the region's XamlPackage (`mathcad/xaml/FlowDocumentN.XamlPackage`) |
| Tag | `tag="..."` attribute on `<region>` (areas included); no spaces or dots |
| Link | `<Hyperlink NavigateUri="#tag">` or `"file.mcdx#tag"` in the XamlPackage |
| Area | `<Area AreaHeight="n"><regions>...</regions></Area>`; child region coordinates are relative to the area |
| Page break | `<pageBreak />` region, always at the end of the page (page = 864 px content + 2 px break, Letter) |
| Include | `<reference href last-saved-date [item-idref]>`. The `last-saved-date` is required or Prime refuses to open the file. `item-idref` points at a cached `mathcad/include/includeN.xml` of the definitions. **With a cache Prime uses it and does not re-read the live file on open** (only the Include's refresh button does); **without one it reads the live file**. CSV disciplines are written with a cache; blank/hand-written ones without, since their definitions are unknown. |
| Input/Output designation | `mathcad/integration.xml`: `ioTagType="Input"` + `<inputAliases>`, or `"Output"` + `<outputAliases>` |
| Results | Prime stores results only for displayed evaluations. Definitions alone get none. |

Facts learned the hard way (each is also commented next to the code that depends on it):

- Prime reuses cached results unless `result.xml` is empty; the builder writes empty `resultData` and Prime computes on open.
- The COM `Open` returns `None` (not an error) for a file it cannot parse. `CastTo(ws, "IMathcadPrimeWorksheet3")` is needed to call `Close`, `Synchronize`, `SaveAs`.
- `SaveAs` with a `.pdf` or `.xps` extension exports that format.
- Unit names accepted by Prime 12.0.1.0 were tested; the list is `VALID_UNITS` in `csv_import.py`. Add to it only after testing in Prime
  (e.g. `kVA`, `kohm`, `kJ`, `kWh`, `%`, `AWG` are rejected).
- Prime keeps running for a few seconds after the last worksheet closes; files stay locked until it exits.
- Use `.venv\Scripts\python.exe` (or `python -m pip`) rather than a bare `pip`; on some PCs they point at different Pythons.

## Not yet done

- Collapsed-area state (the probe was saved expanded, so the attribute is unknown).
- Clicking links cannot be tested through COM; link text matches what Prime itself wrote.
- Function calls in formulas (`sqrt`, `cos`, ...): the XML for them has not been captured, so such rows stay fixed values.
- Letter paper only; margins and fonts come from the skeleton.

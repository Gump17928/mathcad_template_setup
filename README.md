# MathCAD Template

Sets up a linked package of Mathcad Prime worksheets for a project:

- **One worksheet per discipline** (Structural, Electrical, ...): title block, contents with links, one section per calculation, summary.
- **A master worksheet**: title page, contents that link into every discipline file, and a combined summary that reads live values from each discipline file.

You describe each discipline's calculation in a **CSV file** (Excel can edit it). No programming needed.

## First-time setup (once per PC)

1. Install **Python 3.10 or newer** if you don't have it: <https://www.python.org/downloads/>
   (tick *"Add python.exe to PATH"* on the first installer screen).
2. Double-click **`setup.bat`**. It creates a private environment and installs what it needs (internet required, ~1 minute).

Mathcad Prime must be installed to open the results, and for `check_in_prime.bat` and `make_pdfs.bat`.
Building the worksheets does not need Prime.

## Everyday use

| Step | What to do |
|---|---|
| 1. New project | Double-click **`new_project.bat`** and answer the questions. It creates `projects\<project>\` with a starter CSV per discipline. |
| 2. Fill in the calculations | Open `projects\<project>\calcs\<Discipline>.csv` in Excel and replace the starter rows (format below). |
| 3. Build | Double-click **`build.bat`** (pick the project if asked). The worksheets appear in `projects\<project>\output\`; the folder opens for you. |
| 4. Open | Double-click `Master.mcdx` in Prime. Ctrl+Click a link to jump. |
| Optional | **`check_in_prime.bat`** opens everything in Prime and lists the calculated results. **`make_pdfs.bat`** writes PDFs to `projects\<project>\pdf\`. |

Rebuilding overwrites the files in `output\`, so keep your edits in the CSVs (or copy a worksheet elsewhere before editing it by hand).
Close the worksheets in Prime before rebuilding.

`projects\Example` is a ready-made project (four disciplines; Electrical comes from `example.csv`). Run `build.bat` on it to see the result.

Git: only the tool, tests and `projects\Example` are tracked. Your own project folders under `projects\` and everything the tool generates (`output\`, `pdf\`) are ignored by `.gitignore`, so proprietary calculations are not committed by accident. Back them up separately, or remove the `projects/*` lines from `.gitignore` if you want to track them in a private repository.

## The CSV format

First row is the header. Only `section` and `label` are required; the other columns are optional.

| Column | Meaning |
|---|---|
| `section` | Rows with the same section form one calculation block (e.g. `LOAD`, `AMPACITY`). Blocks appear in the order they first show up. |
| `label` | Description shown next to the value. Write `Design current (I_design)` to name the variable inside the brackets. |
| `name` | Variable name (optional; use it instead of the brackets). Letters, digits and `_`, starting with a letter. |
| `value` | A number, or text (text is just displayed). |
| `unit` | `A`, `V`, `kN/m`, `kN*m`, `in^2`, `ohm/1000ft`, ... Units Mathcad doesn't know (`%`, `AWG/kcmil`, `kVA`, `kWh`) are kept as a note and the number is used without a unit. |
| `equation` | `I_design = I_RLA * k_cont` makes a **live formula** in Mathcad. See below. |
| `substituted` | The equation with numbers filled in, shown as a note. |
| `nec_ref` (or `reference`, `ref`) | Code reference, shown as a note. |
| `source` (or `notes`) | Any other note. |
| `status` | `PASS` / `FAIL` etc., shown as a note and listed in the summaries. |

Lines starting with `#` are ignored. Variable names are given the discipline's prefix (`ELE_I_design`) so that disciplines can reuse names.

### What becomes a live Mathcad formula?

An `equation` becomes a live formula when all of these are true:

- it is `name = expression` where `name` is the row's own variable,
- the expression is plain arithmetic: numbers, variables, `+ - * / ^` and brackets,
- every variable in it was defined on an **earlier row** (in worksheet order),
- if the row also has a `value`, the formula agrees with it within 1 %.

Otherwise the value is kept as a fixed number and the equation is shown as a note (this covers table look-ups, `sqrt`, `acos`, `if`, etc.).
`build.bat` prints a short report of what it did with each CSV and which rows it could not make live; it is also saved as `output\import_report.txt`.

Rows with a `value` and no `equation` (or `(input)` in it) are **inputs**: they are registered as designated inputs in Mathcad's Input/Output list, so other programs can set them. Live formulas are registered as designated outputs.

### Choosing what goes in the summary

By default the summary lists every live formula plus every row that has a `status`. To pick specific results, add a `"summary"` list for the discipline in `project.json`:

    {"name": "Electrical", "key": "ELE", "csv": "calcs/Electrical.csv", "summary": ["I_design", "Vd", "Vd_pct"]}

`project.json` is also where you can give sections friendlier names: `"section_titles": {"VDROP": "Voltage drop"}`.

## Things to know

- `status` values (PASS/FAIL) come from the CSV as typed. They do **not** update if you change an input in Mathcad.
- Contents page numbers come from this tool's own page layout, not from Prime. If you edit the worksheet by hand and pages shift, the numbers can be off.
- A calculation block taller than one page is split into several Areas (Mathcad cannot split an Area across pages).
- Links between files (master to disciplines) use relative names, so keep the `output` folder together.
- Mathcad Express can open and calculate these worksheets; it shows `= ?` for premium functions only.

## Troubleshooting

| Message | Fix |
|---|---|
| "Please double-click setup.bat first" | Run `setup.bat` once. |
| "Python is not installed" | Install Python (see setup) and run `setup.bat` again. |
| `ERROR: ... line N: 'section' and 'label' must both be filled in` | Fix that CSV line. |
| "formula gives X but the CSV says Y" | Not an error: the row is kept as a fixed number. Fix the equation or value if it was unexpected. |
| Prime says it can't open a worksheet / the Include is red | Rebuild so the files are regenerated together; keep all `.mcdx` files in the same folder. |

Developer notes (file format details, how to extend): `tool\DEVELOPER_NOTES.md`. Coding rules for changing the code: `tool\CODING_RULES.md`.
Run `run_tests.bat` to check that everything still works after any change.

# MathCAD Template

Sets up a linked package of Mathcad Prime worksheets for a project:

- **One worksheet per discipline** (Structural, Electrical, ...): title block, contents with links, a calculation area and a summary.
- **A master worksheet**: title page, contents that link into every discipline file, and a combined summary that pulls in the results from each discipline file.

There are two ways to fill a discipline, and you can mix them in one project:

- **Blank template (the default).** The tool creates an empty discipline worksheet and you write the calculations in Mathcad Prime yourself. Nothing else is needed. The master's summary lists whichever results you mark as outputs.
- **From a CSV file** (Excel can edit it). The tool turns each row into Mathcad inputs, formulas and notes. See "The CSV format" below. Handy when calculations come out of another tool, but never required.

## First-time setup (once per PC)

1. Install **Python 3.10 or newer** if you don't have it: <https://www.python.org/downloads/>
   (tick *"Add python.exe to PATH"* on the first installer screen). It does not need to be on the PATH, and the Microsoft Store is not needed.
2. Double-click **`setup.bat`**. It looks for Python (the `py` launcher, the PATH, the Windows registry, the usual install folders, a `python` folder next to the file), creates a private environment and installs what it needs (internet required, ~1 minute).
   - **Python in an unusual place?** If it isn't found, `setup.bat` asks you to type the path to `python.exe` (or its folder) and remembers it in `python_path.txt`. You can also run `setup.bat "D:\Tools\Python"` or set the `MATHCAD_PYTHON` environment variable.
   - It needs a **full** Python install, not the "embeddable" zip (that one has no `venv`/`pip`).
   - If the project folder was copied from another PC, `setup.bat` rebuilds the `.venv` folder automatically.

Mathcad Prime must be installed to open the results, and for `check_in_prime.bat` and `make_pdfs.bat`.
Building the worksheets does not need Prime.

## Everyday use

| Step | What to do |
|---|---|
| 1. New project | Double-click **`new_project.bat`** and answer the questions. When asked about starter CSV files, answer `n` for blank templates (default) or `y` to get a CSV per discipline. |
| 2. Build | Double-click **`build.bat`** (pick the project if asked). The worksheets appear in `projects\<project>\output\`; the folder opens for you. |
| 3. Write the calculations | **Blank template:** open each discipline worksheet in Prime and write your calculations there. Select each key result and use *Input/Output > Assign Outputs*, then save. **CSV:** edit `projects\<project>\calcs\<Discipline>.csv` in Excel (format below) and build again. |
| 4. Build again | Run **`build.bat`** again whenever you like. The master is rebuilt and picks up your designated outputs. |
| 5. Open | Double-click `Master.mcdx` in Prime. Ctrl+Click a link to jump. |
| Optional | **`check_in_prime.bat`** opens everything in Prime and lists the calculated results. **`make_pdfs.bat`** writes PDFs to `projects\<project>\pdf\`. |

Rebuilding **never overwrites** a discipline worksheet that has no CSV: the blank template is written once, and after that your file is kept (to start over, delete it from `output\` and build again). Worksheets generated from a CSV, and the master, **are** rewritten every time, so keep edits to those in the CSV. Close the worksheets in Prime before rebuilding.

### How a blank discipline feeds the master

- The master includes each discipline file, and its combined summary lists the **outputs you designated** in that file (with the unit each is shown in). If there are none yet, it says so.
- Use **unique variable names across disciplines**, for example a discipline prefix such as `STR_` or `ELE_`. The master shares one namespace, so a name defined in two disciplines silently takes the value of the one included last. The build report warns about names that appear as outputs in more than one.
- The master's contents link to the *Calculations* and *Summary* headings of the blank template. If you restructure the file, keep those headings' tags, or the links won't land.
- After you change a discipline file, rebuild, or click the refresh button on that Include in the master.

`projects\Example` is a ready-made project (four disciplines, all from CSV files; Electrical comes from `example.csv`). Run `build.bat` on it to see the result.

Git: only the tool, tests and `projects\Example` are tracked. Your own project folders under `projects\` and everything the tool generates (`output\`, `pdf\`) are ignored by `.gitignore`, so proprietary calculations are not committed by accident. Back them up separately, or remove the `projects/*` lines from `.gitignore` if you want to track them in a private repository.

## The CSV format

Only needed for disciplines that you give a CSV (add `"csv": "calcs/Name.csv"` to the discipline in `project.json`; leave it out for a blank template).

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

## Using an older Mathcad Prime (for example Prime 10)

Every worksheet this tool writes is stamped as made by a particular Prime version, and its settings use what that
version knows. The tool ships with a **Prime 12** template. A different Prime may refuse files written in another
version's format, so build the project from a template made by that Prime. It takes five minutes, once per version:

1. **On the PC with the other Prime** (Prime 10, say): start a new worksheet, type a line of text in it, then add a
   line of text to its **header** and its **footer** (double-click the top and bottom margins, or *Document* tab >
   *Headers and Footers*). Save it as, for example, `sample.mcdx`. Any small worksheet is fine, but it must have all three.
2. Copy `sample.mcdx` to the PC where you build worksheets (or do step 3 on the same PC if it has this tool and Python).
3. **Drag `sample.mcdx` onto `capture_skeleton.bat`.** It reads the Prime version from the file, saves
   `tool\skeleton\prime10.mcdx` (author names removed) and prints the version stamps of each template.
   If the sample is unusable it says why (for example "the sample has no header and footer").
4. In the project's `project.json` add `"prime_version": "10"` (the wizard asks for it once a second template exists), then run `build.bat`.

If Prime 10 still refuses a worksheet, save one small worksheet from it that uses the feature that fails (a tag, a link,
an area, an include, a designated input/output) and use it to compare with what this tool writes (see `tool\DEVELOPER_NOTES.md`).
Prime 10 predates some Prime 11/12 features. The tool writes tags, internal links, areas, includes and designated inputs/outputs, which should all exist in Prime 10 (tags and links arrived in Prime 9, links between files in Prime 10), but that has **not been tested on a real Prime 10**.

Commit `tool\skeleton\prime10.mcdx` to the repository so everyone else can build for Prime 10 without repeating the capture.

## Troubleshooting

| Message | Fix |
|---|---|
| "Please double-click setup.bat first" | Run `setup.bat` once. |
| "Python is not installed" / "No Python was chosen" | Install Python (see setup), or run `setup.bat "full\path\to\python.exe"` if it is installed somewhere unusual. |
| "That did not work: ... is not Python 3.10 or newer" | That path is an older Python, or not Python at all. Point it at a 3.10+ install. |
| "The packages did not install" | `setup.bat` needs internet. Behind a company proxy, set the `HTTPS_PROXY` environment variable or ask IT; pip must be allowed to reach pypi.org. |
| `ERROR: ... line N: 'section' and 'label' must both be filled in` | Fix that CSV line. |
| "formula gives X but the CSV says Y" | Not an error: the row is kept as a fixed number. Fix the equation or value if it was unexpected. |
| Prime says it can't open a worksheet / the Include is red | Rebuild so the files are regenerated together; keep all `.mcdx` files in the same folder. For a blank-template discipline, rebuilding keeps your file: if that file is the problem, restore a backup or delete it from `output\` and build again for a fresh blank. |
| The master says "No designated outputs found" for a discipline | In that discipline's worksheet in Prime, select each key result, use *Input/Output > Assign Outputs*, save, and run `build.bat` again. |

Developer notes (file format details, how to extend): `tool\DEVELOPER_NOTES.md`. Coding rules for changing the code: `tool\CODING_RULES.md`.
Run `run_tests.bat` to check that everything still works after any change.

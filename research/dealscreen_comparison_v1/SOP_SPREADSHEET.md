# Workflow A: spreadsheet SOP (a typical manual BD screening process)

You work as a BD analyst would with Excel and public sources. Build one workbook (write it with
Python/openpyxl or pandas, but treat it as Excel: sheets, columns, filters, formulas you would type).

1. **Tracker sheet.** One row per landscape row. Copy the source columns. Add columns:
   `Same molecule as` (row ids), `Target fit`, `Modality fit`, `Indication fit`, `Phase fit`,
   `Scientific call (IN/OUT/UNRESOLVED)`, `Reason`, `Evidence (URL + quote)`.
2. **Filter** by target, modality, indication and phase per the buyer statement. Record every
   judgement in the row; never silently delete rows.
3. **Rights sheet** for every IN row: originator, current U.S. rights holder, licensee(s) and
   territories, marketing status, development status, availability (only if a source says so),
   each with URL + verbatim quote. Unknown stays "unknown".
4. **Shortlist sheet:** up to 10, with why attractive, key risks, open questions.
5. **Valuation sheet:** up to 3 programs, a simple risk-adjusted NPV you build with formulas
   (inputs on the sheet, labelled HYPOTHETICAL), base/bear/bull, and a license vs acquisition note.
6. **Memo** (one page) for a Head of BD.

#!/usr/bin/env python3
"""Fill the commissioner's entry form (Choix<Event>.xlsx) with picks.

  .venv/bin/python fill_entry_form.py data/ChoixShanghai.xlsx \\
      --name "Noah Chamberland" \\
      --picks Alcaraz Tiafoe Tien Khachanov Cerúndolo \\
      --alts Zverev Fils Nakashima Rublev Lehečka \\
      [--out "ChoixShanghai - Noah Chamberland.xlsx"] [--verify-excel]

The form's dropdowns are Excel form controls (combo boxes). Each stores
the selected item's position in a linked cell on the InputChoix sheet.
openpyxl drops form controls on save, so this edits the .xlsx (a zip of
XML) directly. It changes only the linked cells, each control's selected
item, and a flag so Excel recalculates on open; every other part of the
file is copied unchanged. Alternates are paired by row: alternate k
replaces pick k if that pick withdraws before R1.

Everything is read from the form itself (control -> linked cell -> list
range), so the same tool works for any event's form. --verify-excel
(macOS) opens a scratch copy in Excel, recalculates, prints what the
commissioner's formulas resolve to, and closes it without saving.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from openpyxl import load_workbook

from pool.parsers import norm

BANDS = ("#1-4", "#5-8", "#9-16", "#17-32")


def col_row(ref: str) -> tuple[str, int]:
    m = re.fullmatch(r"\$?([A-Z]+)\$?(\d+)", ref)
    if not m:
        raise ValueError(f"bad cell reference {ref!r}")
    return m.group(1), int(m.group(2))


def split_ref(formula: str) -> tuple[str, str]:
    """"InputChoix!$S$1" / "'Banques (Solde restant)'!$B$3:$B$80" -> (sheet, ref)."""
    sheet, ref = formula.rsplit("!", 1)
    return sheet.strip("'"), ref


def read_controls(z: zipfile.ZipFile) -> list[dict]:
    """Form controls on the VosChoix sheet: name, anchor, link, list range."""
    wb_xml = z.read("xl/workbook.xml").decode("utf8")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf8")
    targets = {m.group(1): m.group(2) for m in re.finditer(
        r'<Relationship[^>]*?Id="(rId\d+)"[^>]*?Target="([^"]+)"', rels)}
    targets.update({m.group(2): m.group(1) for m in re.finditer(
        r'<Relationship[^>]*?Target="([^"]+)"[^>]*?Id="(rId\d+)"', rels)})
    sheets = {re.sub("&gt;", ">", m.group(1)): "xl/" + targets[m.group(2)]
              for m in re.finditer(r'<sheet name="([^"]+)" sheetId="\d+" r:id="(rId\d+)"', wb_xml)}
    vos = sheets["VosChoix"]
    srels = z.read(vos.replace("worksheets/", "worksheets/_rels/") + ".rels").decode("utf8")
    ctrl_of = {}
    for m in re.finditer(r"<Relationship[^>]*>", srels):
        rid = re.search(r'Id="(rId\d+)"', m.group(0))
        tgt = re.search(r'Target="\.\./ctrlProps/([^"]+)"', m.group(0))
        if rid and tgt:
            ctrl_of[rid.group(1)] = "xl/ctrlProps/" + tgt.group(1)
    xml = z.read(vos).decode("utf8")
    out = []
    for m in re.finditer(
            r'<control shapeId="\d+" r:id="(rId\d+)" name="([^"]+)">.*?'
            r"<from><xdr:col>(\d+)</xdr:col><xdr:colOff>\d+</xdr:colOff>"
            r"<xdr:row>(\d+)</xdr:row>.*?<to><xdr:col>\d+</xdr:col>"
            r"<xdr:colOff>\d+</xdr:colOff><xdr:row>(\d+)</xdr:row>", xml, re.S):
        rid, name, col, r0, r1 = m.groups()
        props = z.read(ctrl_of[rid]).decode("utf8")
        link = re.search(r'fmlaLink="([^"]+)"', props).group(1)
        rng = re.search(r'fmlaRange="([^"]+)"', props).group(1)
        out.append({"name": name, "col": int(col), "row": (int(r0) + int(r1)) / 2,
                    "file": ctrl_of[rid], "link": split_ref(link), "range": split_ref(rng)})
    return out, sheets


def position_in(ws, rng: str, key_col: str, wanted: str) -> int:
    """1-based position of `wanted` in a dropdown list whose rows line up
    with `key_col` of the same sheet (InputChoix: list row k = player in B)."""
    (c0, r0), (_, r1) = (col_row(x) for x in rng.split(":"))
    for r in range(r0, r1 + 1):
        v = ws[f"{key_col}{r}"].value
        if v is not None and norm(v) == norm(wanted):
            return r - r0 + 1
    raise SystemExit(f"'{wanted}' is not in this form's list ({key_col}{r0}:{key_col}{r1})")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("form")
    ap.add_argument("--name", required=True)
    ap.add_argument("--picks", nargs=5, required=True)
    ap.add_argument("--alts", nargs=5, default=None)
    ap.add_argument("--out")
    ap.add_argument("--verify-excel", action="store_true")
    a = ap.parse_args()

    names = a.picks + (a.alts or [])
    if len({norm(n) for n in names}) != len(names):
        raise SystemExit("a player appears twice among picks/alternates")
    form = Path(a.form)
    out = Path(a.out) if a.out else form.with_name(f"{form.stem} - {a.name}{form.suffix}")
    if out.resolve() == form.resolve():
        raise SystemExit("refusing to overwrite the template; pass a different --out")

    z = zipfile.ZipFile(form)
    controls, sheets = read_controls(z)
    wb = load_workbook(form, data_only=True)
    ic, bq = wb["InputChoix"], wb["Banques (Solde restant)"]

    name_ctl = [c for c in controls if c["range"][0].startswith("Banques")]
    pick_ctl = sorted((c for c in controls if c not in name_ctl and c["col"] == 1),
                      key=lambda c: c["row"])
    alt_ctl = sorted((c for c in controls if c not in name_ctl and c["col"] == 3),
                     key=lambda c: c["row"])
    if len(name_ctl) != 1 or len(pick_ctl) != 5 or len(alt_ctl) != 5:
        raise SystemExit(f"unexpected form layout: {len(name_ctl)} name / "
                         f"{len(pick_ctl)} pick / {len(alt_ctl)} alternate controls")

    plan = [(name_ctl[0], a.name, position_in(bq, name_ctl[0]["range"][1], "B", a.name))]
    for ctl, p in zip(pick_ctl, a.picks):
        plan.append((ctl, p, position_in(ic, ctl["range"][1], "B", p)))
    for ctl, p in zip(alt_ctl, a.alts or []):
        plan.append((ctl, p, position_in(ic, ctl["range"][1], "B", p)))

    # quota sanity check against this pooler's bank (the form warns too)
    band_of = {norm(ic[f"B{r}"].value): ic[f"C{r}"].value
               for r in range(3, ic.max_row + 1) if ic[f"B{r}"].value}
    bank_row = next(r for r in range(3, bq.max_row + 1)
                    if bq[f"B{r}"].value and norm(bq[f"B{r}"].value) == norm(a.name))
    bank = {b: int(bq.cell(bank_row, 3 + i).value or 0) for i, b in enumerate(BANDS)}
    used = {b: sum(1 for p in a.picks if band_of.get(norm(p)) == b) for b in BANDS}
    over = {b: used[b] - bank[b] for b in BANDS if used[b] > bank[b]}
    if over:
        raise SystemExit(f"picks exceed the bank {bank}: over by {over}")
    for ctl, p in zip(alt_ctl, a.alts or []):
        i = alt_ctl.index(ctl)
        if band_of.get(norm(p)) != band_of.get(norm(a.picks[i])):
            print(f"note: alternate {p} ({band_of.get(norm(p))}) is not in the same band "
                  f"as {a.picks[i]} ({band_of.get(norm(a.picks[i]))})", file=sys.stderr)

    link_sheets = {c["link"][0] for c, _, _ in plan}
    if len(link_sheets) != 1:
        raise SystemExit(f"linked cells span several sheets: {link_sheets}")
    link_xml = sheets[link_sheets.pop()]
    cells = {c["link"][1].replace("$", ""): pos for c, _, pos in plan}
    props = {c["file"]: pos for c, _, pos in plan}

    tmp = out.with_suffix(out.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in z.infolist():
            data = z.read(item.filename)
            if item.filename == link_xml:
                s = data.decode("utf8")
                for cell, v in cells.items():
                    s, n = re.subn(r'(<c r="%s"(?: s="\d+")?>)<v>\d+</v>(</c>)' % cell,
                                   r"\g<1><v>%d</v>\g<2>" % v, s)
                    if n != 1:
                        raise SystemExit(f"linked cell {cell} not found as a number")
                data = s.encode("utf8")
            elif item.filename in props:
                v = props[item.filename]
                s = data.decode("utf8")
                s, n = re.subn(r' sel="\d+"', f' sel="{v}"', s)
                if n != 1:
                    raise SystemExit(f"no selection attribute in {item.filename}")
                s = re.sub(r' val="\d+"', f' val="{max(0, v - 1)}"', s)
                data = s.encode("utf8")
            elif item.filename == "xl/workbook.xml":
                s = data.decode("utf8")
                if "fullCalcOnLoad" not in s:
                    s, n = re.subn(r"<calcPr ", '<calcPr fullCalcOnLoad="1" ', s)
                    if n != 1:
                        raise SystemExit("no calcPr element in workbook.xml")
                data = s.encode("utf8")
            zout.writestr(item, data)
    shutil.move(tmp, out)

    print(f"wrote {out}")
    print(f"  name: {a.name}")
    for i, p in enumerate(a.picks):
        alt = f"  (alternate: {a.alts[i]})" if a.alts else ""
        print(f"  Joueur #{i + 1}: {p} {band_of.get(norm(p))}{alt}")
    print("  bank after: " + "/".join(str(bank[b] - used[b]) for b in BANDS))

    if a.verify_excel:
        verify_in_excel(out)


def verify_in_excel(path: Path):
    """macOS: recalc a scratch copy in Excel and print what the form resolves to."""
    with tempfile.TemporaryDirectory() as d:
        copy = Path(d) / "verify.xlsx"
        shutil.copy(path, copy)
        script = f'''
tell application "Microsoft Excel"
  open (POSIX file "{copy}")
  set wb to active workbook
  calculate full
  set ic to worksheet "InputChoix" of wb
  set vc to worksheet "VosChoix" of wb
  set out to "form name: " & (value of range "R5" of ic) & linefeed
  repeat with c in {{"R1", "T1", "V1", "X1", "Z1", "AC1", "AE1", "AG1", "AI1", "AK1"}}
    set out to out & c & " = " & (value of range c of ic) & linefeed
  end repeat
  repeat with c in {{"E12", "E14", "E16", "E18", "E20"}}
    set w to value of range c of vc
    if w is not "" then set out to out & "WARNING " & c & ": " & w & linefeed
  end repeat
  close wb saving no
  return out
end tell'''
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        print(res.stdout or res.stderr)


if __name__ == "__main__":
    main()

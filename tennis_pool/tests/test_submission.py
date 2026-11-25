"""Commissioner-template export, using only runtime-generated synthetic templates."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import hashlib
from io import BytesIO
from pathlib import Path
import re
import warnings
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
import pytest

from tennis_api.models.canonical import (
    Draw, DrawSlot, EntryKind, Event, EventId, Player, PlayerId, Provenance, Surface, Tour,
)
from tennis_api.models.identity import IdentityRegistry, ReviewedAlias
from tennis_pool.ledger import (
    Accepted, Band, EventTerms, LedgerRecord, Pair, SeasonLedger, Selection, Submitted,
)
from tennis_pool.rules import ProvisionalRulesWarning, UnresolvedRulesError
from tennis_pool.submission import (
    SubmissionExportError, export_submission, read_submission, review_submission,
    submitted_record,
)
from tennis_pool.substitutions import seed_band


START = datetime(2026, 8, 20, tzinfo=timezone.utc)
NOW = START + timedelta(days=2)
DEADLINE = START + timedelta(days=3)
SOURCE = "synthetic-template"
ME, OTHER = "Synthetic Entry A", "Synthetic Entry B"
PRIMARIES = (1, 5, 9, 17, 40)
SUBSTITUTES = (2, 6, 10, 18, 41)
CTRL = b"application/vnd.ms-excel.controlproperties+xml"
NAME_CELLS = {"S1": "R1", "U1": "T1", "W1": "V1", "Y1": "X1", "AA1": "Z1",
              "AD1": "AC1", "AF1": "AE1", "AH1": "AG1", "AJ1": "AI1", "AL1": "AK1"}
PRIMARY_LINKS = (("S1", "G"), ("U1", "H"), ("W1", "I"), ("Y1", "J"), ("AA1", "K"))
SUBSTITUTE_LINKS = (("AD1", "L"), ("AF1", "L"), ("AH1", "L"), ("AJ1", "L"), ("AL1", "L"))

pytestmark = pytest.mark.filterwarnings("ignore::tennis_pool.rules.ProvisionalRulesWarning")


def evidence(at=NOW, key="synthetic"):
    return Provenance(source=SOURCE, source_version="fixture-1", source_record_id=key,
                      observed_at=at, available_at=at, ingested_at=at)


def pid(number):
    return PlayerId(f"atp:p{number}")


def label(number):
    return f"Player {number}"


def band_label(number):
    return {Band.TOP4: "#1-4", Band.TOP8: "#5-8", Band.TOP16: "#9-16", Band.TOP32: "#17-32",
            Band.UNSEEDED: "NC"}[seed_band(number if number <= 32 else None)]


def make_registry(unreviewed=()):
    players = tuple(Player(player_id=pid(i), display_name=label(i), tour=Tour.ATP,
                           provenance=evidence(START)) for i in range(1, 130))
    return IdentityRegistry(revision="synthetic-review-1", players=players, aliases=tuple(
        ReviewedAlias(source=SOURCE, player_id=p.player_id, tour=Tour.ATP, name=p.display_name,
                      reviewed_by="fixture-reviewer", reviewed_at=START, provenance=evidence(START))
        for p in players if p.player_id not in unreviewed))


@pytest.fixture
def registry():
    return make_registry()


def draw(at=NOW - timedelta(hours=2)):
    event = Event(event_id=EventId("test:slam"), name="Synthetic slam", tour=Tour.ATP,
                  start_date=date(2026, 8, 24), end_date=date(2026, 9, 6), surface=Surface.HARD,
                  best_of=5, round_count=7, level="grand_slam", provenance=evidence(START))
    return Draw(event=event, slots=tuple(
        DrawSlot(position=i, kind=EntryKind.PLAYER, player_id=pid(i), seed=i if i <= 32 else None)
        for i in range(1, 129)), provenance=evidence(at))


def pick(number):
    return Selection(player_id=pid(number), band=seed_band(number if number <= 32 else None))


def pairs(primaries=PRIMARIES, substitutes=SUBSTITUTES):
    return tuple(Pair(primary=pick(p), substitute=None if s is None else pick(s))
                 for p, s in zip(primaries, substitutes))


def terms(deadline=DEADLINE, event_id="us_open"):
    return EventTerms(event_id=event_id, deadline=deadline, provenance=evidence(START))


def ledger(*records):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalRulesWarning)
        book = SeasonLedger.create((
            EventTerms(event_id="wimbledon", deadline=START - timedelta(days=50),
                       provenance=evidence(START - timedelta(days=60))),
            terms(),
        ), allow_provisional=True)
    return book.append(*records) if records else book


def history():
    """One accepted Wimbledon Excel sheet: debits a 1-4, 5-8, 9-16 and a 17-32 token."""
    at = START - timedelta(days=52)
    picks = pairs((3, 7, 11, 19, 50), (4, 8, 12, 20, 51))
    return (
        LedgerRecord(record_id="w-sub", entry_id="me", event_id="wimbledon", effective_at=at,
                     evidence=evidence(at, "w-sub"),
                     payload=Submitted(picks=picks, submitted_at=at, excel=True)),
        LedgerRecord(record_id="w-acc", entry_id="me", event_id="wimbledon",
                     effective_at=at + timedelta(hours=1), evidence=evidence(at, "w-acc"),
                     payload=Accepted(submission_id="w-sub", approved_by="synthetic authority")),
    )


def snapshot(book=None, at=NOW - timedelta(hours=1)):
    return (book or ledger(*history())).replay(at)


CHAINED = {"U1": "R1", "W1": "T1", "Y1": "V1", "AA1": "X1"}


def display(r, number, last, bank_end=79, usage_range="$CM$228"):
    """The reference template's display formulas for list row r."""
    lookup = f"VLOOKUP($B{r},ChoixSommaire!$A$3:{usage_range},$S$5+1,FALSE)"
    seed = number if number <= 32 else None
    cells = {}
    for target, column in (("E", "B"), ("F", "C")):
        text = f'IF(ISERROR({lookup}),${column}{r},IF({lookup}=5,"",${column}{r}))'
        if seed is not None:
            index = 3 + (0 if seed <= 4 else 1 if seed <= 8 else 2 if seed <= 16 else 3)
            text = (f"IF(VLOOKUP($S$5,'Banques (Solde restant)'!$A$3:$F${bank_end},{index},FALSE)=0,"
                    f'"",{text})')
        cells[target] = "=" + text
    cells["G"] = f'=F{r}&"  "&E{r}'
    cells["H"] = f'=IF(VLOOKUP($S$1,$D$3:$E${last},2,FALSE)=$E{r},"",$G{r})'
    for previous, column, link in zip("HIJK", "IJKL", ("U", "W", "Y", "AA")):
        cells[column] = (f'=IF({previous}{r}="","",IF(VLOOKUP(${link}$1,$D$3:$E${last},2,FALSE)'
                         f'=$E{r},"",$G{r}))')
    return cells


def template(*, players=None, bank=(3, 3, 3, 3), uses=None, header="Tournois Grand Chelem",
             full_calc=False, macro=False, formula_link=False, controls=None, pad=0,
             tamper=None, drop_link=None, bank_end=79, usage_range="$CM$228",
             usage_formula=None, bank_formula=False, usage_label_formula=False,
             usage_labels=None):
    """A synthetic pick template: dropdown parts, linked cells, banks and use counts."""
    players = list(range(1, 129)) if players is None else players
    uses = {3: 1, 4: 0, 7: 1, 11: 1, 19: 1, 50: 1} if uses is None else uses
    wb = Workbook()
    form = wb.active
    form.title = "VosChoix"
    form["A1"] = "Quel est votre nom ?"
    form["A1"].font = Font(bold=True, size=14)
    form["B10"], form["D10"] = "Vos choix", "Joueurs de remplacement (si forfait)"
    for row in (12, 14, 16, 18, 20):
        form.cell(row, 1, f"Joueur #{(row - 10) // 2}").fill = PatternFill("solid", fgColor="FFFF00")
    validation = DataValidation(type="whole", operator="between", formula1="1", formula2="5")
    validation.add("F12:F20")
    form.add_data_validation(validation)
    form.conditional_formatting.add("E12:E20", CellIsRule(operator="equal", formula=['"x"'],
                                                          fill=PatternFill("solid", fgColor="FF0000")))
    wb.create_sheet("NE PAS UTILISER ->")
    lists = wb.create_sheet("InputChoix")
    last = 2 + len(players) + pad
    for i, number in enumerate(players):
        row = 3 + i
        lists.cell(row, 1, i + 1 if i == 0 else f"=A{row - 1}+1")
        lists.cell(row, 2, label(number))
        lists.cell(row, 3, band_label(number))
        lists.cell(row, 4, 1 if i == 0 else f"=D{row - 1}+1")
        for column, text in display(row, number, last, bank_end, usage_range).items():
            lists[f"{column}{row}"] = text
    lists["G2"], lists["L2"] = "Choix #1", "Remplacements"
    for number, (link, _) in enumerate(PRIMARY_LINKS + SUBSTITUTE_LINKS, 1):
        lists[link] = number
        lookup = f"VLOOKUP(${link[:-1]}1,$D$3:$E${last},2,FALSE)"
        previous = CHAINED.get(link)
        lists[NAME_CELLS[link]] = ("=" + lookup if previous is None
                                   else f'=IF({lookup}={previous},"",{lookup})')
    lists["S5"] = 2
    lists["R5"] = "=VLOOKUP($S$5,'Banques (Solde restant)'!$A$3:$B$79,2,FALSE)"
    if formula_link:
        lists["W1"] = "=1+1"
    for cell, value in (tamper or {}).items():
        lists[cell] = value
    banks = wb.create_sheet("Banques (Solde restant)")
    banks["C1"], banks["H1"] = header, "Nombre de joueurs ATP ayant été choisis 5 fois"
    for column, text in zip("CDEF", ("1-4", "5-8", "9-16", "17-32")):
        banks[f"{column}2"] = text
    for row, (who, remaining) in enumerate(((OTHER, (4, 4, 4, 4)), (ME, bank)), 3):
        banks.append([row - 2, who, *remaining, None, 0, None])
    usage = wb.create_sheet("ChoixSommaire")
    usage.append([30, 4, 4])
    usage.append(["", 50, 50])
    usage.append([None, OTHER, ME])
    usage.append(["Nombre joueurs max 5", 0, 0])
    for number in players:
        usage.append([(usage_labels or {}).get(number, label(number)), 0, uses.get(number, 0)])
        if number == usage_formula:
            usage.cell(usage.max_row, 3, "=IF(InputChoix!$S$5=2,5,4)")
    if bank_formula:
        banks["C4"] = "=1+2"
    if usage_label_formula:
        usage.cell(usage.max_row + 1, 1, '="Player "&(40+1)')
    source = BytesIO()
    wb.save(source)
    wb.close()

    links = controls if controls is not None else [
        (link, f"InputChoix!${column}$3:${column}${last}")
        for link, column in PRIMARY_LINKS + SUBSTITUTE_LINKS
    ] + [("S5", "'Banques (Solde restant)'!$B$3:$B$80")]
    selected = {link: value for value, (link, _) in enumerate(PRIMARY_LINKS + SUBSTITUTE_LINKS, 1)}
    selected["S5"] = 2
    parts = {
        f"xl/ctrlProps/ctrlProp{i}.xml":
            ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
             '<formControlPr xmlns="http://schemas.microsoft.com/office/spreadsheetml/2009/9/main" '
             'objectType="Drop" dropLines="15" dropStyle="combo" dx="22" '
             f'fmlaLink="InputChoix!${link.rstrip("0123456789")}${link.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")}" '
             f'fmlaRange="{source_range}" noThreeD="1" sel="{selected.get(link, 1)}" val="0"/>').encode()
        for i, (link, source_range) in enumerate(links, 1)
    }
    parts["xl/worksheets/_rels/sheet1.xml.rels"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.microsoft.com/office/2007/'
                  f'relationships/ctrlProp" Target="../ctrlProps/ctrlProp{i}.xml"/>'
                  for i in range(1, len(links) + 1))
        + "</Relationships>").encode()
    if macro:
        parts["xl/vbaProject.bin"] = b"synthetic VBA project bytes, never executed"
    output = BytesIO()
    with ZipFile(source) as original, ZipFile(output, "w", ZIP_DEFLATED) as target:
        for member in original.infolist():
            content = original.read(member)
            if member.filename == "[Content_Types].xml":
                content = content.replace(b"</Types>", b"".join(
                    b'<Override PartName="/' + name.encode() + b'" ContentType="' + CTRL + b'"/>'
                    for name in parts if "ctrlProp" in name and name.endswith(".xml")
                ) + b"</Types>")
                if macro:
                    content = content.replace(
                        b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
                        b"application/vnd.ms-excel.sheet.macroEnabled.main+xml")
            if member.filename == "xl/workbook.xml" and not full_calc:
                content = re.sub(rb'\s*fullCalcOnLoad="1"', b"", content)
            if member.filename == "xl/_rels/workbook.xml.rels" and macro:
                content = content.replace(b"</Relationships>", b'<Relationship Id="rId99" '
                    b'Type="http://schemas.microsoft.com/office/2006/relationships/vbaProject" '
                    b'Target="vbaProject.bin"/></Relationships>')
            if member.filename == "xl/worksheets/sheet1.xml":
                content = content.replace(b"</worksheet>", ANCHORS)
            if member.filename == "xl/worksheets/sheet3.xml" and drop_link:
                content = re.sub(rb'<c r="' + drop_link.encode() + rb'"[^>]*>.*?</c>', b"", content)
            target.writestr(member, content)
        for name, content in parts.items():
            target.writestr(name, content)
    return output.getvalue()


ANCHORS = (
    b'<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
    b'<mc:Choice Requires="x14" xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/'
    b'spreadsheetDrawing"><controls><control shapeId="2049" name="Drop Down 1"><controlPr>'
    b'<anchor><from><xdr:col>1</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>11</xdr:row>'
    b'<xdr:rowOff>0</xdr:rowOff></from><to><xdr:col>2</xdr:col><xdr:colOff>0</xdr:colOff>'
    b'<xdr:row>2</xdr:row><xdr:rowOff>0</xdr:rowOff></to></anchor></controlPr></control>'
    b'</controls></mc:Choice></mc:AlternateContent></worksheet>'
)


def write(tmp_path, data, name="template.xlsx"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def review(tmp_path, registry, data=None, *, name="template.xlsx", **kwargs):
    path = kwargs.pop("path", None) or write(tmp_path, data or template(), name)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    options = dict(pairs=pairs(), participant=ME, draw=draw(), terms=terms(),
                   snapshot=snapshot(), entry_id="me", registry=registry,
                   template_provenance=evidence(NOW - timedelta(hours=3)), now=NOW,
                   event_ids={"test:slam": "us_open"}, template_events={digest: "us_open"},
                   participants={ME: "me", OTHER: "other"}, allow_provisional=True)
    options.update(kwargs)
    return review_submission(path, **options)


def members(data):
    with ZipFile(BytesIO(data)) as archive:
        return [(info.filename, archive.read(info)) for info in archive.infolist()]


def test_clean_review_exports_verified_file_that_preserves_every_other_part(tmp_path, registry):
    data = template()
    result = review(tmp_path, registry, data)
    assert result.exportable and result.problems == () and result.warnings == ()
    assert result.bank.remaining == (3, 3, 3, 3)
    assert result.bank.after_primaries == (2, 2, 2, 2)
    assert result.bank.worst_case == (2, 2, 2, 2)
    assert result.bank.template == (3, 3, 3, 3)
    assert result.confirmed_qualifying_events == 1
    assert [slot.primary_uses for slot in result.slots] == [0, 0, 0, 0, 0]
    assert ME not in repr(result) and ME not in result.describe()
    assert "template.xlsx" not in repr(result)

    output = tmp_path / "filled.xlsx"
    exported = export_submission(result, output, now=NOW + timedelta(minutes=5))
    assert exported.pairs == pairs()
    assert exported.reimported.participant == ME
    assert exported.reimported.bank_kind == "slam"
    assert "xl/worksheets/sheet3.xml" in exported.changed_members
    assert "xl/workbook.xml" in exported.changed_members
    before, after = members(data), members(output.read_bytes())
    assert [name for name, _ in before] == [name for name, _ in after]
    for (name, old), (_, new) in zip(before, after):
        if name not in exported.changed_members:
            assert old == new, name
    assert exported.preserved_members == len(before) - len(exported.changed_members)
    assert re.search(rb'<calcPr[^>]*fullCalcOnLoad="1"', dict(after)["xl/workbook.xml"])

    # Styles, validation and conditional formatting survive and the file still opens.
    wb = load_workbook(output)
    form = wb["VosChoix"]
    assert form["A1"].font.bold and form["A12"].fill.fgColor.rgb.endswith("FFFF00")
    assert [str(v.sqref) for v in form.data_validations.dataValidation] == ["F12:F20"]
    assert [str(r.sqref) for r in form.conditional_formatting] == ["E12:E20"]
    assert [wb["InputChoix"][link].value for link, _ in PRIMARY_LINKS] == [1, 5, 9, 17, 40]
    assert [wb["InputChoix"][link].value for link, _ in SUBSTITUTE_LINKS] == [2, 6, 10, 18, 41]
    assert wb["InputChoix"]["S5"].value == 2
    wb.close()

    sheet = read_submission(output, registry=registry, provenance=evidence())
    assert sheet.pairs == pairs() and sheet.participant == ME
    assert sheet.players_digest == result.players_digest


def test_xlsm_macros_are_copied_as_opaque_bytes_and_never_loaded(tmp_path, registry):
    data = template(macro=True)
    result = review(tmp_path, registry, data, name="template.xlsm")
    with pytest.raises(SubmissionExportError, match="output_suffix_must_match_template"):
        export_submission(result, tmp_path / "filled.xlsx", now=NOW)
    exported = export_submission(result, tmp_path / "filled.xlsm", now=NOW)
    after = dict(members(exported.output_path.read_bytes()))
    assert after["xl/vbaProject.bin"] == dict(members(data))["xl/vbaProject.bin"]
    assert after["[Content_Types].xml"] == dict(members(data))["[Content_Types].xml"]
    assert b"macroEnabled" in after["[Content_Types].xml"]
    assert "xl/vbaProject.bin" not in exported.changed_members


def test_existing_recalculation_flag_and_matching_selections_are_left_untouched(tmp_path, registry):
    result = review(tmp_path, registry, template(full_calc=True))
    exported = export_submission(result, tmp_path / "out.xlsx", now=NOW)
    assert "xl/workbook.xml" not in exported.changed_members


@pytest.mark.parametrize("bad, message", [
    (pairs((1, 1, 9, 17, 40)), "distinct primaries"),
    (pairs(substitutes=(5, 6, 10, 18, 41)), "same selection band"),
    (pairs((1, 2, 3, 4, 40), (None, None, None, None, 41)), "slam bank 1-4 has 3 left; needs 4"),
    (pairs()[:4], "exactly five slot pairs"),
])
def test_illegal_rosters_are_blocked_and_nothing_is_written(tmp_path, registry, bad, message):
    result = review(tmp_path, registry, pairs=bad)
    assert not result.exportable
    assert any(message in problem for problem in result.problems), result.problems
    with pytest.raises(SubmissionExportError, match="review_has_problems"):
        export_submission(result, tmp_path / "out.xlsx", now=NOW)
    assert not (tmp_path / "out.xlsx").exists()


def test_unresolved_players_participant_and_empty_substitutes_block(tmp_path, registry):
    missing = template(players=list(range(1, 128)) + [129])
    result = review(tmp_path, registry, missing, pairs=pairs((1, 5, 9, 17, 128)))
    assert any("atp:p128 is missing from the template" in p for p in result.problems)
    assert any("not in the draw" in w for w in result.warnings)
    assert any("missing from the template" in w for w in result.warnings)

    result = review(tmp_path, registry, participant="Somebody Else")
    assert "Participant label matches no unique template participant" in result.problems

    result = review(tmp_path, registry, pairs=pairs(substitutes=(2, 6, None, 18, 41)))
    assert any("Slot 3 has no substitute" in p for p in result.problems)

    result = review(tmp_path, make_registry(unreviewed=(pid(1),)))
    assert any("lack a reviewed alias" in w for w in result.warnings)
    assert any("atp:p1 is missing from the template" in p for p in result.problems)


def test_template_semantics_that_would_blank_a_pick_block_export(tmp_path, registry):
    result = review(tmp_path, registry, template(bank=(3, 0, 3, 3)))
    assert any("no 5-8 tokens left" in p for p in result.problems)
    assert any("differs from the ledger bank" in w for w in result.warnings)

    result = review(tmp_path, registry, template(uses={3: 1, 7: 1, 11: 1, 19: 1, 50: 1, 41: 5}))
    assert any("five uses for atp:p41" in p for p in result.problems)
    assert any("ledger shows 0" in w for w in result.warnings)

    result = review(tmp_path, registry, template(bank=(1, 3, 3, 3)),
                    pairs=pairs((1, 2, 9, 17, 40), (3, 4, 10, 18, 41)))
    assert any("Template shows 1 1-4 token(s) left; the sheet uses 2" in p
               for p in result.problems)

    result = review(tmp_path, registry, template(header="Tournois Masters", bank=(3, 3, 3, 3)))
    assert any("masters event" in p for p in result.problems)


def test_template_band_disagreeing_with_draw_blocks_that_pick(tmp_path, registry):
    data = template()
    # Reseeded draw: player 40 is now seeded 32, so the template's NC label is stale.
    slots = tuple(replace(slot, seed=None) if slot.seed == 32 else
                  replace(slot, seed=32) if slot.player_id == pid(40) else slot
                  for slot in draw().slots)
    reseeded = replace(draw(), slots=slots)
    bad = pairs((1, 5, 9, 17, 40), (2, 6, 10, 18, 31))
    bad = tuple(Pair(primary=Selection(player_id=p.primary.player_id, band=Band.TOP32)
                     if p.primary.player_id == pid(40) else p.primary, substitute=p.substitute)
                for p in bad)
    result = review(tmp_path, registry, data, draw=reseeded, pairs=bad)
    assert any("Template lists atp:p40 in band NF, not 17-32" in p for p in result.problems)
    assert any("Template band differs from the draw seed" in w for w in result.warnings)


def test_deadlines_and_stale_or_future_inputs(tmp_path, registry):
    late = review(tmp_path, registry, terms=terms(deadline=NOW - timedelta(minutes=1)))
    assert any("has passed" in p for p in late.problems)

    soon = review(tmp_path, registry, terms=terms(deadline=NOW + timedelta(minutes=30)))
    assert soon.exportable and any("Deadline is 0.5 h away" in w for w in soon.warnings)
    with pytest.raises(SubmissionExportError, match="deadline_passed"):
        export_submission(soon, tmp_path / "out.xlsx", now=NOW + timedelta(minutes=31))

    stale = review(tmp_path, registry, draw=draw(NOW - timedelta(days=2)),
                   snapshot=snapshot(at=NOW - timedelta(days=2)),
                   template_provenance=evidence(NOW - timedelta(days=3)))
    assert stale.exportable
    assert {w.split(" is ")[0] for w in stale.warnings} >= {"Draw", "Ledger snapshot", "Template"}

    future = review(tmp_path, registry, draw=draw(NOW + timedelta(hours=1)))
    assert "Draw is dated after the review time" in future.problems

    fresh = review(tmp_path, registry)
    with pytest.raises(SubmissionExportError, match="review_stale"):
        export_submission(fresh, tmp_path / "out.xlsx", now=NOW + timedelta(days=1, seconds=1))
    with pytest.raises(SubmissionExportError, match="review_stale"):
        export_submission(fresh, tmp_path / "out.xlsx", now=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="timezone"):
        review(tmp_path, registry, now=NOW.replace(tzinfo=None))


def test_changed_template_and_existing_output_are_refused(tmp_path, registry):
    path = write(tmp_path, template())
    result = review(tmp_path, registry, path=path)
    output = tmp_path / "out.xlsx"
    output.write_bytes(b"keep me")
    with pytest.raises(SubmissionExportError, match="output_exists"):
        export_submission(result, output, now=NOW)
    assert output.read_bytes() == b"keep me"
    path.write_bytes(template(bank=(3, 3, 3, 2)))
    with pytest.raises(SubmissionExportError, match="template_changed_since_review"):
        export_submission(result, tmp_path / "other.xlsx", now=NOW)


def test_prior_submissions_and_acceptance_are_flagged(tmp_path, registry):
    at = NOW - timedelta(hours=5)
    sent = LedgerRecord(record_id="u-sub", entry_id="me", event_id="us_open", effective_at=at,
                        evidence=evidence(at, "u-sub"),
                        payload=Submitted(picks=pairs(), submitted_at=at, excel=True))
    result = review(tmp_path, registry, snapshot=snapshot(ledger(*history(), sent)))
    assert any("1 earlier submission(s)" in w for w in result.warnings)
    accepted = LedgerRecord(record_id="u-acc", entry_id="me", event_id="us_open", effective_at=at,
                            evidence=evidence(at, "u-acc"),
                            payload=Accepted(submission_id="u-sub", approved_by="synthetic"))
    result = review(tmp_path, registry, snapshot=snapshot(ledger(*history(), sent, accepted)))
    assert any("accepted sheet already exists" in w for w in result.warnings)

    result = review(tmp_path, registry, snapshot=snapshot(ledger()), data=template(bank=(4, 4, 4, 4)))
    assert any("full banks and no uses assumed" in w for w in result.warnings)


def test_export_neither_consumes_season_state_nor_claims_the_excel_bonus(tmp_path, registry):
    book = ledger(*history())
    before = book.replay(NOW + timedelta(hours=1))
    exported = export_submission(review(tmp_path, registry, snapshot=book.replay(NOW)),
                                 tmp_path / "out.xlsx", now=NOW)
    assert book.replay(NOW + timedelta(hours=1)) == before

    sent_at = NOW + timedelta(minutes=10)
    with pytest.raises(ValueError, match="before it was exported"):
        submitted_record(exported, record_id="x", sent_at=NOW - timedelta(seconds=1),
                         evidence=evidence(NOW))
    with pytest.raises(ValueError, match="after the deadline"):
        submitted_record(exported, record_id="x", sent_at=DEADLINE,
                         evidence=evidence(DEADLINE))
    record = submitted_record(exported, record_id="u-sub", sent_at=sent_at,
                              evidence=evidence(sent_at, "u-sub"))
    assert record.payload == Submitted(picks=pairs(), submitted_at=sent_at, excel=True)
    assert (record.entry_id, record.event_id) == ("me", "us_open")
    submitted = book.append(record).replay(sent_at + timedelta(hours=1))
    mine = next(e for e in submitted.entries if e.entry_id == "me")
    old = next(e for e in before.entries if e.entry_id == "me")
    assert (mine.slam, mine.usage, mine.qualifying_events) == (old.slam, old.usage,
                                                               old.qualifying_events)
    state = next(s for s in submitted.events if s.event_id == "us_open")
    assert state.accepted_submission_id is None and not state.qualifying_excel

    acceptance = LedgerRecord(record_id="u-acc", entry_id="me", event_id="us_open",
                              effective_at=sent_at + timedelta(hours=2),
                              evidence=evidence(sent_at + timedelta(hours=2), "u-acc"),
                              payload=Accepted(submission_id="u-sub", approved_by="synthetic"))
    accepted = book.append(record, acceptance).replay(sent_at + timedelta(hours=3))
    mine = next(e for e in accepted.entries if e.entry_id == "me")
    assert mine.slam == (2, 2, 2, 2)
    assert mine.qualifying_events == ("wimbledon", "us_open")


def test_strict_mode_blocks_and_opt_in_must_be_boolean(tmp_path, registry):
    with pytest.raises(UnresolvedRulesError):
        review(tmp_path, registry, allow_provisional=False)
    with pytest.raises(ValueError, match="explicit boolean"):
        review(tmp_path, registry, allow_provisional=1)


@pytest.mark.parametrize("data, code", [
    (lambda: template(controls=[("S1", "InputChoix!$G$3:$G$130")]), "unsupported_template_controls"),
    (lambda: template(formula_link=True), "template_link_cell_not_constant"),
    (lambda: b"Private participant content", "invalid_template"),
])
def test_unsupported_templates_fail_with_safe_reason_codes(tmp_path, registry, data, code):
    with pytest.raises(SubmissionExportError) as error:
        review(tmp_path, registry, data(), name="Synthetic Entry A.xlsx")
    assert str(error.value) == code
    assert error.value.__cause__ is None


def test_reimport_rejects_controls_that_disagree_with_their_linked_cells(tmp_path, registry):
    exported = export_submission(review(tmp_path, registry), tmp_path / "out.xlsx", now=NOW)
    output = BytesIO()
    with ZipFile(exported.output_path) as source, ZipFile(output, "w") as target:
        for info in source.infolist():
            content = source.read(info)
            if b'fmlaLink="InputChoix!$S$1"' in content:
                content = re.sub(rb'sel="\d+"', b'sel="3"', content)
            target.writestr(info, content)
    path = write(tmp_path, output.getvalue(), "tampered.xlsx")
    with pytest.raises(SubmissionExportError, match="template_selection_unset_or_inconsistent"):
        read_submission(path, registry=registry, provenance=evidence())


def test_padded_list_rows_are_allowed_but_never_selected(tmp_path, registry):
    exported = export_submission(review(tmp_path, registry, template(pad=8)),
                                 tmp_path / "out.xlsx", now=NOW)
    assert exported.pairs == pairs()


def test_correction_is_checked_against_the_state_before_the_sheet_it_replaces(tmp_path, registry):
    at = NOW - timedelta(hours=5)
    first = pairs((1, 2, 9, 17, 40), (3, 4, 10, 18, 41))
    sent = LedgerRecord(record_id="u-sub", entry_id="me", event_id="us_open", effective_at=at,
                        evidence=evidence(at, "u-sub"),
                        payload=Submitted(picks=first, submitted_at=at, excel=True))
    accepted = LedgerRecord(record_id="u-acc", entry_id="me", event_id="us_open", effective_at=at,
                            evidence=evidence(at, "u-acc"),
                            payload=Accepted(submission_id="u-sub", approved_by="synthetic"))
    book = ledger(*history(), sent, accepted)
    mine = next(e for e in book.replay(NOW).entries if e.entry_id == "me")
    assert mine.slam[0] == 1    # the accepted sheet already spent two 1-4 tokens
    result = review(tmp_path, registry, snapshot=snapshot(book), pairs=first)
    assert result.exportable, result.problems
    assert result.bank.remaining == (3, 3, 3, 3)
    assert [slot.primary_uses for slot in result.slots] == [0, 0, 0, 0, 0]


def test_draw_must_fit_the_event_format_dates_and_template_list(tmp_path, registry):
    masters = replace(draw(), event=replace(draw().event, best_of=3))
    assert any("Draw format does not match us_open" in p
               for p in review(tmp_path, registry, draw=masters).problems)
    later = replace(draw(), event=replace(draw().event, start_date=date(2026, 10, 1),
                                          end_date=date(2026, 10, 12)))
    assert any("Draw dates do not fit" in p for p in review(tmp_path, registry, draw=later).problems)
    other = review(tmp_path, registry, template(players=list(range(1, 100))))
    assert "Template player list does not match this draw" in other.problems


@pytest.mark.parametrize("tamper", [
    {"E3": '="Player 2"'},
    {"H5": "=$G6"},
    {"R1": "=VLOOKUP($S1,$D$3:$E$130,2,FALSE)&\"x\""},
    {"T1": "=VLOOKUP($U1,$D$3:$E$130,2,FALSE)"},
])
def test_display_formulas_that_could_show_another_name_are_rejected(tmp_path, registry, tamper):
    with pytest.raises(SubmissionExportError, match="unsupported_template_formulas"):
        review(tmp_path, registry, template(tamper=tamper))


def test_dropdown_ranges_beyond_the_row_limit_are_rejected(tmp_path, registry):
    links = [(link, f"InputChoix!${column}$3:${column}$20000")
             for link, column in PRIMARY_LINKS + SUBSTITUTE_LINKS]
    links.append(("S5", "'Banques (Solde restant)'!$B$3:$B$80"))
    with pytest.raises(SubmissionExportError, match="unsupported_template_controls"):
        review(tmp_path, registry, template(controls=links))


def test_absent_linked_cell_blocks_the_review_not_just_the_export(tmp_path, registry):
    result = review(tmp_path, registry, template(drop_link="S1"))
    assert "Template cannot record this sheet (template_link_cell_absent)" in result.problems


def test_correction_keeping_a_player_whose_fifth_use_it_recorded(tmp_path, registry):
    earlier = (("australian_open", 200), ("indian_wells", 170), ("miami", 150),
               ("wimbledon", 50))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalRulesWarning)
        book = SeasonLedger.create(tuple(
            EventTerms(event_id=event, deadline=START - timedelta(days=days),
                       provenance=evidence(START - timedelta(days=days + 5)))
            for event, days in earlier) + (terms(),), allow_provisional=True)
    records = []
    for event, days in earlier:
        at = START - timedelta(days=days + 1)
        records += [
            LedgerRecord(record_id=f"{event}-sub", entry_id="me", event_id=event, effective_at=at,
                         evidence=evidence(at, f"{event}-sub"), payload=Submitted(
                             picks=pairs((40, 41, 42, 43, 44), (None,) * 5),
                             submitted_at=at, excel=True)),
            LedgerRecord(record_id=f"{event}-acc", entry_id="me", event_id=event, effective_at=at,
                         evidence=evidence(at, f"{event}-acc"),
                         payload=Accepted(submission_id=f"{event}-sub", approved_by="synthetic")),
        ]
    at = NOW - timedelta(hours=5)
    sheet = pairs((1, 5, 9, 17, 40), (2, 6, 10, 18, 45))
    records += [
        LedgerRecord(record_id="u-sub", entry_id="me", event_id="us_open", effective_at=at,
                     evidence=evidence(at, "u-sub"),
                     payload=Submitted(picks=sheet, submitted_at=at, excel=True)),
        LedgerRecord(record_id="u-acc", entry_id="me", event_id="us_open", effective_at=at,
                     evidence=evidence(at, "u-acc"),
                     payload=Accepted(submission_id="u-sub", approved_by="synthetic")),
    ]
    book = book.append(*records)
    assert dict(next(e for e in book.replay(NOW).entries if e.entry_id == "me").usage)[pid(40)] == 5
    data = template(bank=(4, 4, 4, 4), uses={n: 4 for n in (40, 41, 42, 43, 44)})
    result = review(tmp_path, registry, data, snapshot=snapshot(book), pairs=sheet)
    assert result.exportable, result.problems
    assert result.slots[4].primary_uses == 4
    assert not any("uses for" in w for w in result.warnings)


def test_draw_event_must_map_to_the_requested_event(tmp_path, registry):
    for mapping in ({}, {"test:slam": "wimbledon"}):
        result = review(tmp_path, registry, event_ids=mapping)
        assert any("does not map the draw's event to us_open" in p for p in result.problems)


def test_same_kind_template_from_another_event_is_blocked(tmp_path, registry):
    other = list(range(1, 33)) + list(range(200, 232)) + list(range(65, 129))
    result = review(tmp_path, registry, template(players=other))
    assert "Template player list does not match this draw" in result.problems


def test_list_numbering_must_start_at_one_in_row_three(tmp_path, registry):
    with pytest.raises(SubmissionExportError, match="unsupported_template_player_list"):
        review(tmp_path, registry, template(tamper={"D2": 1, "D3": "=D2+1"}))


def test_template_must_be_bound_to_the_event_even_with_an_identical_list(tmp_path, registry):
    data = template()    # same kind and the same player list as the US Open draw
    digest = hashlib.sha256(data).hexdigest()
    for binding in ({}, {digest: "wimbledon"}):
        result = review(tmp_path, registry, data, template_events=binding)
        assert any("does not tie this template to us_open" in p for p in result.problems)
        with pytest.raises(SubmissionExportError, match="review_has_problems"):
            export_submission(result, tmp_path / "out.xlsx", now=NOW)


def test_participant_must_map_to_the_reviewed_entry(tmp_path, registry):
    for mapping in ({}, {ME: "other", OTHER: "me"}):
        result = review(tmp_path, registry, participants=mapping)
        assert ("Reviewed participant mapping does not tie this participant to the entry"
                in result.problems)


def test_computed_bank_or_use_counts_cannot_approve_a_pick(tmp_path, registry):
    result = review(tmp_path, registry, template(usage_formula=41))
    assert any("use count for atp:p41 is computed by a formula" in p for p in result.problems)
    result = review(tmp_path, registry, template(bank_formula=True))
    assert any("bank for this participant is computed" in p for p in result.problems)


@pytest.mark.parametrize("options", [{"bank_end": 3}, {"usage_range": "$B$228"}])
def test_lookup_ranges_must_reach_every_participant(tmp_path, registry, options):
    with pytest.raises(SubmissionExportError, match="unsupported_template_formulas"):
        review(tmp_path, registry, template(**options))


def test_use_counts_outside_the_lookup_range_are_not_read(tmp_path, registry):
    # Row 45 (player 41) lies past $CM$10, so Excel shows the name and ignores the count.
    result = review(tmp_path, registry, template(usage_range="$CM$10", uses={41: 5}))
    assert not any("five uses" in p for p in result.problems)
    assert result.slots[4].template_substitute_uses == 0
    assert result.exportable, result.problems


def leftovers(tmp_path):
    return sorted(path.name for path in tmp_path.iterdir() if path.name.startswith(".submission-"))


def test_read_back_differing_from_the_written_bytes_publishes_nothing(
        tmp_path, registry, monkeypatch):
    import tennis_pool.submission as module

    result = review(tmp_path, registry)
    output = tmp_path / "out.xlsx"
    real = module._read_staged
    monkeypatch.setattr(module, "_read_staged",
                        lambda folder, name, limits: real(folder, name, limits) + b"\0")
    with pytest.raises(SubmissionExportError, match="output_changed_after_write"):
        export_submission(result, output, now=NOW)
    assert not output.exists() and leftovers(tmp_path) == []


def test_failed_write_publishes_nothing_and_leaves_no_staged_file(tmp_path, registry, monkeypatch):
    import tennis_pool.submission as module

    result = review(tmp_path, registry)
    output = tmp_path / "out.xlsx"
    real = module.os.fdopen

    class Failing:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.handle.close()

        def fileno(self):
            return self.handle.fileno()

        def write(self, _):
            raise OSError("disk full")

    monkeypatch.setattr(module.os, "fdopen", lambda fd, mode: Failing(real(fd, mode)) if mode == "wb" else real(fd, mode))
    with pytest.raises(SubmissionExportError, match="output_not_writable"):
        export_submission(result, output, now=NOW)
    assert not output.exists() and leftovers(tmp_path) == []


def test_a_file_appearing_at_the_output_path_is_never_overwritten_or_removed(
        tmp_path, registry, monkeypatch):
    import tennis_pool.submission as module

    result = review(tmp_path, registry)
    output = tmp_path / "out.xlsx"
    real = module.os.fdopen

    class Racing:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.handle.close()

        def fileno(self):
            return self.handle.fileno()

        def write(self, data):
            output.write_bytes(b"someone else's file")
            return self.handle.write(data)

    monkeypatch.setattr(module.os, "fdopen", lambda fd, mode: Racing(real(fd, mode)) if mode == "wb" else real(fd, mode))
    with pytest.raises(SubmissionExportError, match="output_exists"):
        export_submission(result, output, now=NOW)
    assert output.read_bytes() == b"someone else's file"
    assert leftovers(tmp_path) == []


def test_exported_file_is_readable_and_no_staged_file_remains(tmp_path, registry, monkeypatch):
    import tennis_pool.submission as module

    folders = []
    real = module.tempfile.mkdtemp

    def recording(**kwargs):
        folders.append(Path(real(**kwargs)))
        assert folders[-1].stat().st_mode & 0o777 == 0o700
        return str(folders[-1])

    monkeypatch.setattr(module.tempfile, "mkdtemp", recording)
    exported = export_submission(review(tmp_path, registry), tmp_path / "out.xlsx", now=NOW)
    assert len(folders) == 1 and not folders[0].exists()
    mode = exported.output_path.stat().st_mode
    assert mode & 0o400 and not mode & 0o077    # owner-only: it names the participant
    assert leftovers(tmp_path) == []


def test_computed_labels_in_the_usage_lookup_column_are_rejected(tmp_path, registry):
    with pytest.raises(SubmissionExportError, match="unsupported_template_usage"):
        review(tmp_path, registry, template(usage_label_formula=True))


def test_an_unverified_staging_folder_is_never_cleaned_up(tmp_path, registry, monkeypatch):
    import tennis_pool.submission as module

    result = review(tmp_path, registry)
    swapped = tmp_path / ".submission-swapped"
    swapped.mkdir()
    swapped.chmod(0o777)
    (swapped / "export.xlsx").write_bytes(b"not ours")
    monkeypatch.setattr(module.tempfile, "mkdtemp", lambda **kwargs: str(swapped))
    with pytest.raises(SubmissionExportError, match="output_not_writable"):
        export_submission(result, tmp_path / "out.xlsx", now=NOW)
    assert (swapped / "export.xlsx").read_bytes() == b"not ours"
    assert not (tmp_path / "out.xlsx").exists()


def test_a_used_seeded_band_without_a_stored_template_count_blocks(tmp_path, registry):
    result = review(tmp_path, registry, template(bank=(3, None, 3, 3)))
    assert any("bank for 5-8 has no stored count" in p for p in result.problems)
    assert review(tmp_path, registry, template(bank=(3, 3, 3, 3))).exportable


def test_lookup_ranges_ending_outside_the_sheet_are_rejected(tmp_path, registry):
    for usage_range in ("$CM$0", "$CM$1048577"):
        with pytest.raises(SubmissionExportError, match="unsupported_template_formulas"):
            review(tmp_path, registry, template(usage_range=usage_range))


def test_use_counts_match_labels_case_insensitively_like_excel(tmp_path, registry):
    result = review(tmp_path, registry,
                    template(uses={41: 5}, usage_labels={41: "PLAYER 41"}))
    assert any("five uses for atp:p41" in p for p in result.problems)


def test_wildcard_characters_in_list_labels_are_rejected(tmp_path, registry):
    with pytest.raises(SubmissionExportError, match="unsupported_template_player_list"):
        review(tmp_path, registry, template(tamper={"B3": "Play?r 1"}))


def test_an_uninspectable_output_path_returns_a_safe_error(tmp_path, registry, monkeypatch):
    result = review(tmp_path, registry)

    def denied(self, *args, **kwargs):
        raise PermissionError("private path")

    monkeypatch.setattr(Path, "exists", denied)
    with pytest.raises(SubmissionExportError) as error:
        export_submission(result, tmp_path / "out.xlsx", now=NOW)
    assert str(error.value) == "output_not_writable" and error.value.__cause__ is None

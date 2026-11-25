"""Fill the commissioner's pick template locally; never send, submit or accept.

The 2026 template (``VosChoix`` sheet) records a sheet as eleven form-control
dropdowns: one for the participant, five primaries and five paired substitutes.
Each dropdown stores a 1-based list index in its control part and in a linked
``InputChoix`` cell. Export copies every ZIP member of the template byte for
byte and rewrites only those indices plus the workbook's recalculate-on-open
flag, so styles, validation, conditional formats, controls and any VBA project
are preserved. Macros are copied as opaque bytes and never loaded or run.

Exporting writes a local file. It does not record a submission, accept a sheet,
debit a bank, consume a player use or establish Excel-bonus eligibility: those
need ledger evidence of what was actually sent and what the commissioner accepted.
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import posixpath
import re
import warnings
from typing import Any, Mapping
from xml.etree import ElementTree
from zipfile import ZipFile, ZipInfo

from tennis_api.models.canonical import Draw, PlayerId, Provenance, Tour
from tennis_api.models.identity import IdentityRegistry, IdentityResolutionError
from tennis_pool.ledger import (
    _SEEDED, _SLAMS, Band, EventTerms, LedgerRecord, LedgerSnapshot, Pair,
    Selection, Submitted,
)
from tennis_pool.rules import DEPENDENCIES, require_resolved
from tennis_pool.substitutions import RosterCheck, seed_band, validate_roster
from tennis_pool.workbooks import WorkbookImportError, WorkbookLimits, _bounded_bytes, _check_archive


_REGISTER_VERSION = "2026-provisional-2"
# Digest of the implemented submission decision texts; changes need review.
_DECISION_DIGEST = "d2fd2dcf5c7cf87c5530dec3aa1736ff81197d99ddee99bbfaa2aabfcfb6936e"

_FORM, _LISTS, _BANKS, _USAGE = "VosChoix", "InputChoix", "Banques (Solde restant)", "ChoixSommaire"
# (linked InputChoix cell, list column) per slot, in VosChoix row order.
_PRIMARY_LINKS = (("S1", "G"), ("U1", "H"), ("W1", "I"), ("Y1", "J"), ("AA1", "K"))
_SUBSTITUTE_LINKS = (("AD1", "L"), ("AF1", "L"), ("AH1", "L"), ("AJ1", "L"), ("AL1", "L"))
_PARTICIPANT_LINK = "S5"
_BAND_LABELS = {"#1-4": Band.TOP4, "#5-8": Band.TOP8, "#9-16": Band.TOP16,
                "#17-32": Band.TOP32, "NC": Band.UNSEEDED}
_BANK_HEADERS = {"Tournois Grand Chelem": "slam", "Tournois Masters": "masters"}
_FULL_BANKS = {"slam": (4, 4, 4, 4), "masters": (9, 9, 9, 7)}
_FIRST_ROW = 3

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_DOC_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_RANGE = re.compile(
    r"(?:'((?:[^']|'')+)'|([^'!]+))!\$?([A-Z]+)\$?([1-9][0-9]*)(?::\$?([A-Z]+)\$?([1-9][0-9]*))?"
)


class SubmissionExportError(ValueError):
    """Safe reason codes only: no filenames, participant labels or cell values."""


def _gate(
    allow_provisional: bool, register_path: str | Path | None,
) -> tuple[str, tuple[tuple[str, str, str], ...]]:
    if type(allow_provisional) is not bool:
        raise ValueError("Provisional submission rules require an explicit boolean opt-in")
    register = require_resolved("submission", register_path, allow_provisional=allow_provisional)
    keys = DEPENDENCIES["submission"]
    digest = hashlib.sha256(json.dumps(
        {key: register["decisions"][key]["decision"] for key in keys}, sort_keys=True,
    ).encode()).hexdigest()
    if register["register_version"] != _REGISTER_VERSION or digest != _DECISION_DIGEST:
        raise ValueError("Unsupported submission rule version; implementation review required")
    return register["register_version"], tuple(
        (key, register["decisions"][key]["status"], register["decisions"][key]["decision"])
        for key in keys
    )


# --------------------------------------------------------------------------- template


@dataclass(frozen=True)
class _Template:
    digest: str
    bank_kind: str
    control_parts: dict[str, str]           # linked cell -> ctrlProp member
    selections: dict[str, int | None]       # linked cell -> control's selected index
    links: dict[str, int | None]            # linked cell -> InputChoix cell value
    lists_part: str
    labels: tuple[tuple[str, Band], ...]    # list index - 1 -> (label, band)
    participants: tuple[str, ...]           # participant index - 1 -> label
    banks: tuple[tuple[int | None, ...], ...]
    usage_headers: tuple[Any, ...]
    usage: dict[str, tuple[Any, ...]]
    repeated_usage: frozenset[str]

    @property
    def players_digest(self) -> str:
        return hashlib.sha256(json.dumps(
            [[label, band.value] for label, band in self.labels],
        ).encode()).hexdigest()


def _column(letters: str) -> int:
    number = 0
    for char in letters:
        number = number * 26 + ord(char) - ord("A") + 1
    return number


def _reference(text: str | None) -> tuple[str, str, int, str | None, int | None]:
    match = _RANGE.fullmatch(text or "")
    if match is None:
        raise SubmissionExportError("unsupported_template_controls")
    sheet = match[1].replace("''", "'") if match[1] is not None else match[2]
    return (sheet, match[3], int(match[4]), match[5],
            None if match[6] is None else int(match[6]))


def _part(base: str, target: str) -> str:
    if target.startswith("/"):
        return posixpath.normpath(target.lstrip("/"))
    return posixpath.normpath(posixpath.join(posixpath.dirname(base), target))


def _rels(archive: ZipFile, part: str) -> dict[str, tuple[str, str]]:
    path = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
    if path not in archive.namelist():
        return {}
    rels = {}
    for node in ElementTree.fromstring(archive.read(path)).iter(_PKG_REL + "Relationship"):
        if node.get("TargetMode") == "External":
            continue  # never followed; copied verbatim on export
        rels[node.get("Id", "")] = (node.get("Type", ""), _part(part, node.get("Target", "")))
    return rels


def _rows(book: Any, name: str) -> list[tuple[Any, ...]]:
    sheet = book[name]
    sheet.reset_dimensions()
    rows = [tuple(cell.value for cell in row) for row in sheet.iter_rows()]
    width = max((len(row) for row in rows), default=0)
    return [row + (None,) * (width - len(row)) for row in rows]


def _cell(rows: list[tuple[Any, ...]], row: int, column: int) -> Any:
    """1-based lookup that treats cells outside the stored area as empty."""
    if row > len(rows) or column > len(rows[row - 1]):
        return None
    return rows[row - 1][column - 1]


def _count(value: Any, maximum: int) -> int | None:
    if type(value) in (int, float) and int(value) == value and 0 <= value <= maximum:
        return int(value)
    return None


def _label(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _read_template(data: bytes, limits: WorkbookLimits) -> _Template:
    from openpyxl import load_workbook

    _check_archive(data, limits)
    with ZipFile(BytesIO(data)) as archive:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relations = _rels(archive, "xl/workbook.xml")
        parts = {}
        for node in workbook.iter(_MAIN + "sheet"):
            kind, target = relations.get(node.get(_DOC_REL + "id", ""), ("", ""))
            if kind.endswith("/worksheet"):
                parts[node.get("name", "")] = target
        if any(name not in parts for name in (_FORM, _LISTS, _BANKS)):
            raise SubmissionExportError("unsupported_template_layout")
        control_parts: dict[str, str] = {}
        selections: dict[str, int | None] = {}
        ranges: dict[str, tuple[str, str, int, str | None, int | None]] = {}
        for kind, target in _rels(archive, parts[_FORM]).values():
            if not kind.endswith("/ctrlProp"):
                continue
            if target not in archive.namelist():
                raise SubmissionExportError("unsupported_template_controls")
            control = ElementTree.fromstring(archive.read(target))
            if control.tag.rsplit("}", 1)[-1] != "formControlPr" or control.get("objectType") != "Drop":
                raise SubmissionExportError("unsupported_template_controls")
            sheet, column, row, end_column, end_row = _reference(control.get("fmlaLink"))
            if sheet != _LISTS or end_column is not None:
                raise SubmissionExportError("unsupported_template_controls")
            link = column + str(row)
            if link in control_parts:
                raise SubmissionExportError("unsupported_template_controls")
            control_parts[link] = target
            ranges[link] = _reference(control.get("fmlaRange"))
            selected = control.get("sel")
            selections[link] = int(selected) if selected is not None and selected.isdigit() else None
    expected = {link for link, _ in _PRIMARY_LINKS + _SUBSTITUTE_LINKS} | {_PARTICIPANT_LINK}
    if set(control_parts) != expected:
        raise SubmissionExportError("unsupported_template_controls")
    list_end = {ranges[link][4] for link, _ in _PRIMARY_LINKS + _SUBSTITUTE_LINKS}
    if len(list_end) != 1 or any(
        ranges[link][:4] != (_LISTS, column, _FIRST_ROW, column)
        for link, column in _PRIMARY_LINKS + _SUBSTITUTE_LINKS
    ) or ranges[_PARTICIPANT_LINK][:4] != (_BANKS, "B", _FIRST_ROW, "B"):
        raise SubmissionExportError("unsupported_template_controls")
    last_row = list_end.pop()
    participant_end = ranges[_PARTICIPANT_LINK][4]
    if (last_row is None or participant_end is None
            or not _FIRST_ROW <= last_row <= limits.rows
            or not _FIRST_ROW <= participant_end <= limits.rows):
        raise SubmissionExportError("unsupported_template_controls")

    with ExitStack() as stack:
        values = load_workbook(BytesIO(data), read_only=True, data_only=True,
                               keep_links=False, keep_vba=False)
        stack.callback(values.close)
        formulas = load_workbook(BytesIO(data), read_only=True, data_only=False,
                                 keep_links=False, keep_vba=False)
        stack.callback(formulas.close)
        lists, list_formulas = _rows(values, _LISTS), _rows(formulas, _LISTS)
        banks, bank_formulas = _rows(values, _BANKS), _rows(formulas, _BANKS)
        if _USAGE not in values.sheetnames:
            raise SubmissionExportError("unsupported_template_layout")
        usage_rows = _rows(values, _USAGE)

    links = {}
    for link in expected:
        column, row = link.rstrip("0123456789"), int(link.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
        if isinstance(_cell(list_formulas, row, _column(column)), str):
            raise SubmissionExportError("template_link_cell_not_constant")
        links[link] = _count(_cell(lists, row, _column(column)), 100_000)

    labels: list[tuple[str, Band]] = []
    for row in range(_FIRST_ROW, last_row + 1):
        name, band = _cell(list_formulas, row, 2), _cell(list_formulas, row, 3)
        index = _cell(list_formulas, row, 4)
        if name is None and band in (None, *_BAND_LABELS):
            break  # padding rows may keep a band label but never a name
        # Labels must be stored constants; the D column must number rows from 1.
        if (_label(name) is None or name.startswith("=") or band not in _BAND_LABELS
                or index != (1 if row == _FIRST_ROW else f"=D{row - 1}+1")):
            raise SubmissionExportError("unsupported_template_player_list")
        labels.append((name.strip(), _BAND_LABELS[band]))
    if any(_cell(list_formulas, row, 2) is not None
           or _cell(list_formulas, row, 3) not in (None, *_BAND_LABELS)
           for row in range(_FIRST_ROW + len(labels), last_row + 1)):
        raise SubmissionExportError("unsupported_template_player_list")
    if not labels:
        raise SubmissionExportError("unsupported_template_player_list")
    _check_display(list_formulas, labels)

    header = _cell(bank_formulas, 1, 3)
    if (header not in _BANK_HEADERS or tuple(
            str(_cell(bank_formulas, 2, column)).lstrip("#") for column in range(3, 7)
    ) != ("1-4", "5-8", "9-16", "17-32")):
        raise SubmissionExportError("unsupported_template_banks")
    participants: list[str] = []
    bank_rows: list[tuple[int | None, ...]] = []
    for row in range(_FIRST_ROW, participant_end + 1):
        name = _cell(bank_formulas, row, 2)
        if name is None:
            break
        if _label(name) is None or name.startswith("=") or _cell(bank_formulas, row, 1) != row - 2:
            raise SubmissionExportError("unsupported_template_participants")
        participants.append(name.strip())
        maxima = _FULL_BANKS[_BANK_HEADERS[header]]
        bank_rows.append(tuple(_count(_cell(banks, row, column), maxima[column - 3])
                               for column in range(3, 7)))
    if not participants:
        raise SubmissionExportError("unsupported_template_participants")

    if len(usage_rows) < 3:
        raise SubmissionExportError("unsupported_template_usage")
    usage_headers = usage_rows[2]
    usage: dict[str, tuple[Any, ...]] = {}
    repeated: set[str] = set()
    for record in usage_rows[4:]:
        player = _label(record[0])
        if player is not None:
            # VLOOKUP reads the first matching row; remember ambiguous labels.
            if player in usage:
                repeated.add(player)
            usage.setdefault(player, record)
    return _Template(
        digest=hashlib.sha256(data).hexdigest(), bank_kind=_BANK_HEADERS[header],
        control_parts=control_parts, selections=selections, links=links,
        lists_part=parts[_LISTS], labels=tuple(labels), participants=tuple(participants),
        banks=tuple(bank_rows), usage_headers=usage_headers, usage=usage,
        repeated_usage=frozenset(repeated),
    )


_USAGE_LOOKUP = "VLOOKUP($B{r},ChoixSommaire!$A$3:{usage},$S$5+1,FALSE)"
_SHOWN = 'IF(ISERROR({lookup}),${column}{r},IF({lookup}=5,"",${column}{r}))'
_BANK_GUARD = "IF(VLOOKUP($S$5,'Banques (Solde restant)'!$A$3:{bank},{index},FALSE)=0,\"\",{shown})"
_NAME_CELLS = {"S1": ("R1", None), "U1": ("T1", "R1"), "W1": ("V1", "T1"), "Y1": ("X1", "V1"),
               "AA1": ("Z1", "X1"), "AD1": ("AC1", None), "AF1": ("AE1", None),
               "AH1": ("AG1", None), "AJ1": ("AI1", None), "AL1": ("AK1", None)}


def _check_display(rows: list[tuple[Any, ...]], labels: list[tuple[str, Band]]) -> None:
    """Pin every formula that turns a selected index into a shown pick name.

    The 2026 template shows list row ``r`` through E (label or blank), F (band
    or blank), G (both) and the dropdown lists H to L, and the picked names in
    row 1 through VLOOKUPs on D:E. Only this exact layout is accepted, so the
    exported workbook cannot display a name other than the verified label.
    """
    first = _cell(rows, 1, _column("R"))
    match = re.fullmatch(r"=VLOOKUP\(\$S1,\$D\$3:\$E\$([0-9]+),2,FALSE\)", str(first))
    found = re.search(r"ChoixSommaire!\$A\$3:(\$[A-Z]+\$[0-9]+)", str(_cell(rows, 3, 5)))
    guard = next((re.search(r"!\$A\$3:(\$F\$[0-9]+),", str(_cell(rows, r, 5)))
                  for r in range(_FIRST_ROW, _FIRST_ROW + len(labels))
                  if labels[r - _FIRST_ROW][1] is not Band.UNSEEDED), None)
    if (match is None or found is None or int(match[1]) < _FIRST_ROW + len(labels) - 1
            or (guard is None and any(band is not Band.UNSEEDED for _, band in labels))):
        raise SubmissionExportError("unsupported_template_formulas")
    lookup_range = f"$D$3:$E${match[1]}"
    for link, (cell, previous) in _NAME_CELLS.items():
        lookup = f"VLOOKUP(${link[:-1]}1,{lookup_range},2,FALSE)"
        expected = ("=" + lookup if previous is None
                    else f'=IF({lookup}={previous},"",{lookup})')
        row, column = int(cell.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")), cell.rstrip("0123456789")
        if _cell(rows, row, _column(column)) != expected:
            raise SubmissionExportError("unsupported_template_formulas")
    links = [link for link, _ in _PRIMARY_LINKS]
    for r, (_, band) in enumerate(labels, _FIRST_ROW):
        shown = {}
        for column in "BC":
            lookup = _USAGE_LOOKUP.format(r=r, usage=found[1])
            text = _SHOWN.format(lookup=lookup, column=column, r=r)
            if band is not Band.UNSEEDED and guard is not None:
                text = _BANK_GUARD.format(bank=guard[1], index=3 + _SEEDED.index(band), shown=text)
            shown[column] = "=" + text
        cells = {
            "E": shown["B"], "F": shown["C"], "G": f'=F{r}&"  "&E{r}',
            "H": f'=IF(VLOOKUP(${links[0][:-1]}$1,{lookup_range},2,FALSE)=$E{r},"",$G{r})',
        }
        for previous, column, link in zip("HIJK", "IJKL", links[1:]):
            cells[column] = (f'=IF({previous}{r}="","",IF(VLOOKUP(${link[:-1]}$1,'
                                f'{lookup_range},2,FALSE)=$E{r},"",$G{r}))')
        if any(_cell(rows, r, _column(column)) != text for column, text in cells.items()):
            raise SubmissionExportError("unsupported_template_formulas")


def _guarded(call: Any) -> Any:
    """Run a parser step, reducing any third-party error to a safe reason code."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return call()
    except (SubmissionExportError, WorkbookImportError) as error:
        reason = str(error)
    except IdentityResolutionError:
        reason = "identity_requires_review"
    except ImportError:
        reason = "excel_dependency_required"
    except Exception:
        reason = "invalid_template"
    raise SubmissionExportError(reason) from None


# --------------------------------------------------------------------------- re-import


@dataclass(frozen=True)
class SubmissionSheet:
    """What a filled template says, read back from its dropdown indices."""

    participant: str = field(repr=False)
    bank_kind: str
    pairs: tuple[Pair, ...]
    players_digest: str
    template_digest: str


def _read_sheet(
    data: bytes, registry: IdentityRegistry, provenance: Provenance, limits: WorkbookLimits,
) -> SubmissionSheet:
    template = _read_template(data, limits)

    def index(link: str, size: int) -> int:
        selected, linked = template.selections[link], template.links[link]
        if selected is None or selected != linked or not 1 <= selected <= size:
            raise SubmissionExportError("template_selection_unset_or_inconsistent")
        return selected

    def selection(link: str) -> Selection:
        label, band = template.labels[index(link, len(template.labels)) - 1]
        player = registry.resolve(source=provenance.source, tour=Tour.ATP, name=label)
        return Selection(player_id=player, band=band)

    participant = template.participants[index(_PARTICIPANT_LINK, len(template.participants)) - 1]
    pairs = tuple(Pair(primary=selection(primary), substitute=selection(substitute))
                  for (primary, _), (substitute, _) in zip(_PRIMARY_LINKS, _SUBSTITUTE_LINKS))
    return SubmissionSheet(participant=participant, bank_kind=template.bank_kind, pairs=pairs,
                           players_digest=template.players_digest,
                           template_digest=template.digest)


def read_submission(
    path: str | Path, *, registry: IdentityRegistry, provenance: Provenance,
    limits: WorkbookLimits = WorkbookLimits(),
) -> SubmissionSheet:
    """Re-import a filled template: participant, five pairs and the event's bank kind.

    Indices come from the dropdown controls and must agree with their linked
    cells. Formula caches are never trusted and formulas are never evaluated.
    """
    result: SubmissionSheet = _guarded(
        lambda: _read_sheet(_bounded_bytes(path, limits), registry, provenance, limits))
    return result


# --------------------------------------------------------------------------- review


@dataclass(frozen=True)
class SlotReview:
    slot: int
    primary: Selection
    substitute: Selection | None
    primary_uses: int
    substitute_uses: int | None
    template_primary_uses: int | None
    template_substitute_uses: int | None


@dataclass(frozen=True)
class BankReview:
    kind: str
    remaining: tuple[int, ...]
    after_primaries: tuple[int, ...]
    worst_case: tuple[int, ...]
    template: tuple[int | None, ...]


@dataclass(frozen=True)
class SubmissionReview:
    """Final pre-export review; ``exportable`` only when ``problems`` is empty.

    ``confirmed_qualifying_events`` counts accepted Excel sheets already in the
    ledger. This sheet adds nothing to it until the commissioner accepts it.
    """

    event_id: str
    reviewed_at: datetime
    deadline: datetime
    pairs: tuple[Pair, ...]
    slots: tuple[SlotReview, ...]
    bank: BankReview
    roster: RosterCheck | None
    problems: tuple[str, ...]
    warnings: tuple[str, ...]
    confirmed_qualifying_events: int
    rule_register_version: str
    submission_decisions: tuple[tuple[str, str, str], ...]
    entry_id: str = field(repr=False)
    participant: str = field(repr=False)
    template_path: Path = field(repr=False)
    template_digest: str = field(repr=False)
    players_digest: str = field(repr=False)
    stale_after: timedelta = field(repr=False)
    _edits: tuple[tuple[str, int], ...] = field(repr=False, compare=False)
    _registry: IdentityRegistry = field(repr=False, compare=False)
    _provenance: Provenance = field(repr=False, compare=False)
    _limits: WorkbookLimits = field(repr=False, compare=False)

    @property
    def exportable(self) -> bool:
        return not self.problems

    def describe(self) -> str:
        """Plain-text review without the participant label or file name."""
        lines = [f"Event {self.event_id}; deadline {self.deadline.isoformat()}; "
                 f"reviewed {self.reviewed_at.isoformat()}"]
        for slot in self.slots:
            substitute = ("none" if slot.substitute is None else
                          f"{slot.substitute.player_id} ({slot.substitute.band.value}, "
                          f"{slot.substitute_uses} prior uses)")
            lines.append(f"  {slot.slot}. {slot.primary.player_id} ({slot.primary.band.value}, "
                         f"{slot.primary_uses} prior uses); substitute {substitute}")
        bands = ", ".join(band.value for band in _SEEDED)
        lines.append(f"  {self.bank.kind} bank [{bands}]: {self.bank.remaining} now, "
                     f"{self.bank.after_primaries} after primaries, "
                     f"{self.bank.worst_case} if every substitute activates; "
                     f"template shows {self.bank.template}")
        lines.append(f"  Excel bonus: {self.confirmed_qualifying_events} accepted qualifying "
                     "events; this export claims nothing until accepted")
        lines += ["  PROBLEM: " + problem for problem in self.problems]
        lines += ["  warning: " + warning for warning in self.warnings]
        lines.append("  exportable" if self.exportable else "  NOT exportable")
        return "\n".join(lines)


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(name + " requires a timezone-aware datetime")


def _age(hours: timedelta) -> str:
    return f"{hours.total_seconds() / 3600:.1f} h"


def review_submission(
    template_path: str | Path, *, pairs: tuple[Pair, ...], participant: str, draw: Draw,
    terms: EventTerms, snapshot: LedgerSnapshot, entry_id: str, registry: IdentityRegistry,
    template_provenance: Provenance, now: datetime, event_ids: Mapping[str, str],
    stale_after: timedelta = timedelta(hours=24),
    allow_provisional: bool = False, register_path: str | Path | None = None,
    limits: WorkbookLimits = WorkbookLimits(),
) -> SubmissionReview:
    """Check five slot pairs against the ledger, the draw and the template itself.

    Pairs fill ``Joueur #1``..``#5`` in order, each with its substitute. Problems
    block export: an illegal roster under the replayed ledger state, a player or
    participant the template cannot express, a band the template disagrees with,
    a template bank or five-use count that would make the commissioner's sheet
    blank a pick, inputs dated after ``now`` and a passed deadline. Warnings flag
    inputs older than ``stale_after``, template/ledger disagreements and earlier
    submissions for this event. ``event_ids`` is a reviewed mapping from canonical
    draw event IDs to pool event IDs; the draw's event must map to ``terms``.
    """
    version, decisions = _gate(allow_provisional, register_path)
    _aware(now, "Review time")
    if not isinstance(participant, str) or not participant.strip():
        raise ValueError("Participant label required")
    if type(stale_after) is not timedelta or stale_after <= timedelta(0):
        raise ValueError("stale_after must be a positive timedelta")
    path = Path(template_path)
    data: bytes = _guarded(lambda: _bounded_bytes(path, limits))
    template: _Template = _guarded(lambda: _read_template(data, limits))
    event_id = terms.event_id
    kind = "slam" if event_id in _SLAMS else "masters"
    problems: list[str] = []
    notes: list[str] = []
    if template.bank_kind != kind:
        problems.append(f"Template is for a {template.bank_kind} event, not {event_id}")
    # A reviewed mapping names the draw's pool event; format and dates must fit too.
    if event_ids.get(draw.event.event_id) != event_id:
        problems.append(f"Reviewed event mapping does not map the draw's event to {event_id}")
    rounds = 6 if event_id in ("monte_carlo", "paris") else 7
    if (draw.event.best_of, draw.event.round_count) != ((5 if kind == "slam" else 3), rounds):
        problems.append(f"Draw format does not match {event_id}")
    if not (draw.event.start_date - timedelta(days=7) <= terms.deadline.date()
            <= draw.event.end_date):
        problems.append(f"Draw dates do not fit the {event_id} deadline")

    # Who the template's list rows are, through reviewed aliases only.
    rows: dict[PlayerId, list[int]] = {}
    unresolved = 0
    for i, (label, _) in enumerate(template.labels, 1):
        try:
            player = registry.resolve(source=template_provenance.source, tour=Tour.ATP, name=label)
        except IdentityResolutionError:
            unresolved += 1
            continue
        rows.setdefault(player, []).append(i)
    if unresolved:
        notes.append(f"{unresolved} template player label(s) lack a reviewed alias")
    seeds = {slot.player_id: slot.seed for slot in draw.slots if slot.player_id is not None}
    outside = sum(player not in seeds for player in rows)
    missing = sum(player not in rows for player in seeds)
    differing = sum(player in seeds and template.labels[i[0] - 1][1] is not seed_band(seeds[player])
                    for player, i in rows.items())
    if (outside + missing) * 10 > len(seeds):
        problems.append("Template player list does not match this draw")
    if outside:
        notes.append(f"Template lists {outside} player(s) who are not in the draw")
    if missing:
        notes.append(f"{missing} draw player(s) are missing from the template")
    if differing:
        notes.append(f"Template band differs from the draw seed for {differing} player(s)")

    matches = [i for i, label in enumerate(template.participants, 1) if label == participant.strip()]
    if len(matches) != 1:
        problems.append("Participant label matches no unique template participant")
    participant_index = matches[0] if len(matches) == 1 else None

    # Ledger state at the review cut.
    entry = next((e for e in snapshot.entries if e.entry_id == entry_id), None)
    if entry is None:
        notes.append("Entry has no ledger records at this cutoff; full banks and no uses assumed")
    remaining = _FULL_BANKS[kind] if entry is None else (
        entry.slam if kind == "slam" else entry.masters)
    uses = {} if entry is None else dict(entry.usage)
    for state in snapshot.events:
        if (state.entry_id, state.event_id) == (entry_id, event_id):
            if state.accepted_submission_id is not None:
                notes.append("An accepted sheet already exists for this event; a correction "
                             "replaces it only once the commissioner accepts it")
            elif state.submitted:
                notes.append(f"{len(state.submitted)} earlier submission(s) recorded for this event")
            if state.selections and entry is not None:
                # Replay charges only the final accepted sheet, so check a
                # correction against the state before the one it replaces.
                bank = list(remaining)
                for charged in state.selections:
                    uses[charged.player_id] -= 1
                    if charged.band in _SEEDED:
                        bank[_SEEDED.index(charged.band)] += 1
                remaining = tuple(bank)
                uses = {player: count for player, count in uses.items() if count}
                usage = tuple(sorted(uses.items()))
                entry = (replace(entry, usage=usage, slam=remaining) if kind == "slam"
                         else replace(entry, usage=usage, masters=remaining))

    roster = None
    if len(pairs) != 5 or not all(isinstance(pair, Pair) for pair in pairs):
        problems.append("A submission requires exactly five slot pairs")
    else:
        roster = validate_roster(pairs, draw, event_id, entry,
                                 allow_provisional=allow_provisional, register_path=register_path)
        problems.extend(roster.problems)
        for scenario in roster.scenarios:
            problems.extend(f"If {', '.join(scenario.activated)} activate: {problem}"
                            for problem in scenario.problems)

    # Template semantics: its formulas blank a pick whose band shows no tokens
    # left or whose player shows five uses, and count primaries per band.
    template_bank = (template.banks[participant_index - 1] if participant_index is not None
                     else (None,) * 4)
    template_uses: dict[PlayerId, int | None] = {}
    if participant_index is not None:
        if template_bank != remaining:
            notes.append(f"Template bank {template_bank} differs from the ledger bank {remaining}")
        if (participant_index >= len(template.usage_headers)
                or template.usage_headers[participant_index] != participant.strip()):
            notes.append("Template usage column header does not name this participant")
    edits: list[tuple[str, int]] = []
    slots: list[SlotReview] = []
    for number, pair in enumerate(pairs if roster is not None else (), 1):
        indices = []
        for selection, role in ((pair.primary, "primary"), (pair.substitute, "substitute")):
            if selection is None:
                problems.append(f"Slot {number} has no substitute; this template cannot leave "
                                "a substitute empty")
                continue
            player = selection.player_id
            found = rows.get(player, [])
            if len(found) != 1:
                problems.append(f"{player} is {'missing from' if not found else 'repeated in'} "
                                "the template player list")
                continue
            label, band = template.labels[found[0] - 1]
            indices.append(found[0])
            if band is not selection.band:
                problems.append(f"Template lists {player} in band {band.value}, not "
                                f"{selection.band.value}")
            if participant_index is not None:
                if band in _SEEDED and template_bank[_SEEDED.index(band)] == 0:
                    problems.append(f"Template shows no {band.value} tokens left, so it would "
                                    f"blank {role} {player}")
                row = template.usage.get(label)
                count = (None if row is None or participant_index >= len(row)
                         else _count(row[participant_index], 5))
                template_uses[player] = 0 if row is None else count
                if label in template.repeated_usage:
                    notes.append(f"Template usage repeats the label for {player}; Excel "
                                 "reads its first row")
                if count is not None and count >= 5:
                    problems.append(f"Template shows five uses for {player}, so it would "
                                    f"blank that {role}")
                if count is not None and count != uses.get(player, 0):
                    notes.append(f"Template shows {count} uses for {player}; the ledger "
                                 f"shows {uses.get(player, 0)}")
        if len(indices) == 2:
            edits += [(_PRIMARY_LINKS[number - 1][0], indices[0]),
                      (_SUBSTITUTE_LINKS[number - 1][0], indices[1])]
        substitute = pair.substitute
        slots.append(SlotReview(
            slot=number, primary=pair.primary, substitute=substitute,
            primary_uses=uses.get(pair.primary.player_id, 0),
            substitute_uses=None if substitute is None else uses.get(substitute.player_id, 0),
            template_primary_uses=template_uses.get(pair.primary.player_id),
            template_substitute_uses=(None if substitute is None
                                      else template_uses.get(substitute.player_id)),
        ))
    primaries = [pair.primary.band for pair in pairs] if roster is not None else []
    for i, band in enumerate(_SEEDED):
        available = template_bank[i]
        if available is not None and primaries.count(band) > available:
            problems.append(f"Template shows {available} {band.value} token(s) left; the sheet "
                            f"uses {primaries.count(band)}")
    if participant_index is not None and None in template_bank:
        notes.append("Template bank cells have no stored values; its bank was not checked")
    if participant_index is not None:
        edits.append((_PARTICIPANT_LINK, participant_index))
    if not problems:
        # Dry run: the review passes only if the writer can record this exact
        # sheet in this template and read it back unchanged.
        try:
            output, changed = _fill(data, template, tuple(edits))
            _verify(data, output, changed, _Expected(
                participant.strip(), tuple(pairs), kind, template.players_digest,
                registry, template_provenance, limits))
        except SubmissionExportError as error:
            problems.append(f"Template cannot record this sheet ({error})")

    after = tuple(remaining[i] - primaries.count(band) for i, band in enumerate(_SEEDED))
    worst = after
    if roster is not None and roster.scenarios:
        worst = tuple(min(remaining[i] - sum(s.band is band for s in scenario.selections)
                          for scenario in roster.scenarios) for i, band in enumerate(_SEEDED))

    # Timing.
    if now >= terms.deadline:
        problems.append(f"Deadline {terms.deadline.isoformat()} has passed; a late sheet is not "
                        "a voluntary submission")
    elif terms.deadline - now < timedelta(hours=1):
        notes.append(f"Deadline is {_age(terms.deadline - now)} away")
    for name, moment in (("Draw", draw.provenance.available_at),
                         ("Ledger snapshot", snapshot.cutoff),
                         ("Template", template_provenance.available_at),
                         ("Event terms", terms.provenance.available_at)):
        if moment > now:
            problems.append(f"{name} is dated after the review time")
        elif name != "Event terms" and now - moment > stale_after:
            notes.append(f"{name} is {_age(now - moment)} old (stale after {_age(stale_after)})")

    return SubmissionReview(
        event_id=event_id, reviewed_at=now, deadline=terms.deadline, pairs=tuple(pairs),
        slots=tuple(slots),
        bank=BankReview(kind=kind, remaining=tuple(remaining), after_primaries=after,
                        worst_case=worst, template=tuple(template_bank)),
        roster=roster, problems=tuple(dict.fromkeys(problems)),
        warnings=tuple(dict.fromkeys(notes)),
        confirmed_qualifying_events=0 if entry is None else len(entry.qualifying_events),
        rule_register_version=version, submission_decisions=decisions,
        entry_id=entry_id, participant=participant.strip(), template_path=path,
        template_digest=template.digest,
        players_digest=template.players_digest, stale_after=stale_after,
        _edits=tuple(edits), _registry=registry, _provenance=template_provenance,
        _limits=limits,
    )


# --------------------------------------------------------------------------- export


def _set_cell(xml: bytes, ref: str, value: int) -> bytes:
    found = []
    for match in re.finditer(rb"<c\b[^>]*>", xml):
        attributes = dict(re.findall(rb'([\w:]+)="([^"]*)"', match[0]))
        if attributes.get(b"r") == ref.encode():
            found.append((match, attributes))
    if len(found) != 1:
        raise SubmissionExportError("template_link_cell_absent")
    match, attributes = found[0]
    if attributes.get(b"t", b"n") != b"n":
        raise SubmissionExportError("template_link_cell_not_constant")
    number = b"<v>%d</v>" % value
    if match[0].endswith(b"/>"):
        return xml[:match.start()] + match[0][:-2].rstrip() + b">" + number + b"</c>" + xml[match.end():]
    end = xml.find(b"</c>", match.end())
    if end < 0 or re.fullmatch(rb"(<v>[0-9]+(\.0+)?</v>)?", xml[match.end():end]) is None:
        raise SubmissionExportError("template_link_cell_not_constant")
    return xml[:match.end()] + number + xml[end:]


def _set_attribute(xml: bytes, element: bytes, name: bytes, value: bytes, code: str) -> bytes:
    tags = list(re.finditer(rb"<" + element + rb"\b[^>]*>", xml))
    if len(tags) != 1:
        raise SubmissionExportError(code)
    tag = tags[0][0]
    pattern = rb'(\s' + name + rb'=")[^"]*(")'
    if re.search(pattern, tag):
        new = re.sub(pattern, lambda m: m[1] + value + m[2], tag, count=1)
    else:
        new = tag[:len(element) + 1] + b" " + name + b'="' + value + b'"' + tag[len(element) + 1:]
    return xml[:tags[0].start()] + new + xml[tags[0].end():]


def _fill(
    data: bytes, template: _Template, edits: tuple[tuple[str, int], ...],
) -> tuple[bytes, tuple[str, ...]]:
    if {link for link, _ in edits} != set(template.control_parts) or len(edits) != 11:
        raise SubmissionExportError("incomplete_selection")
    with ZipFile(BytesIO(data)) as source:
        original = {name: source.read(name) for name in
                    {template.lists_part, "xl/workbook.xml", *template.control_parts.values()}}
        replaced = dict(original)
        for link, index in edits:
            part = template.control_parts[link]
            replaced[part] = _set_attribute(replaced[part], b"formControlPr", b"sel",
                                            str(index).encode(), "unsupported_template_controls")
            replaced[template.lists_part] = _set_cell(replaced[template.lists_part], link, index)
        # Cached formula results still describe the old selections; ask Excel to
        # recalculate on open instead of evaluating any formula here.
        replaced["xl/workbook.xml"] = _set_attribute(
            replaced["xl/workbook.xml"], b"calcPr", b"fullCalcOnLoad", b"1",
            "template_calculation_settings_absent")
        output = BytesIO()
        with ZipFile(output, "w") as target:
            for info in source.infolist():
                clone = ZipInfo(info.filename, date_time=info.date_time)
                clone.compress_type = info.compress_type
                clone.external_attr = info.external_attr
                clone.create_system = info.create_system
                clone.comment = info.comment
                target.writestr(clone, replaced.get(info.filename, source.read(info)))
    changed = tuple(sorted(name for name, content in replaced.items()
                           if content != original[name]))
    return output.getvalue(), changed


@dataclass(frozen=True)
class SubmissionExport:
    """A verified local file. Not sent, not submitted and not accepted."""

    review: SubmissionReview
    output_path: Path = field(repr=False)
    output_digest: str
    exported_at: datetime
    changed_members: tuple[str, ...]
    preserved_members: int
    reimported: SubmissionSheet

    @property
    def pairs(self) -> tuple[Pair, ...]:
        return self.reimported.pairs


@dataclass(frozen=True)
class _Expected:
    participant: str = field(repr=False)
    pairs: tuple[Pair, ...]
    kind: str
    players_digest: str
    registry: IdentityRegistry = field(repr=False)
    provenance: Provenance = field(repr=False)
    limits: WorkbookLimits = field(repr=False)


def _verify(data: bytes, output: bytes, changed: tuple[str, ...], expected: _Expected,
            ) -> SubmissionSheet:
    sheet: SubmissionSheet = _guarded(
        lambda: _read_sheet(output, expected.registry, expected.provenance, expected.limits))
    if (sheet.participant != expected.participant or sheet.pairs != expected.pairs
            or sheet.bank_kind != expected.kind
            or sheet.players_digest != expected.players_digest):
        raise SubmissionExportError("reimport_mismatch")
    with ZipFile(BytesIO(data)) as before, ZipFile(BytesIO(output)) as after:
        if [i.filename for i in before.infolist()] != [i.filename for i in after.infolist()]:
            raise SubmissionExportError("reimport_member_mismatch")
        for info in before.infolist():
            if info.filename not in changed and before.read(info) != after.read(info.filename):
                raise SubmissionExportError("reimport_member_mismatch")
    return sheet


def export_submission(
    review: SubmissionReview, output_path: str | Path, *, now: datetime,
) -> SubmissionExport:
    """Write the filled template to a new local file and verify it by re-import.

    Refuses a review with problems, a review older than its ``stale_after``, a
    template changed since review, a passed deadline, an existing output file
    and a suffix other than the template's. Nothing is emailed or recorded.
    """
    _aware(now, "Export time")
    if not review.exportable:
        raise SubmissionExportError("review_has_problems")
    if now < review.reviewed_at or now - review.reviewed_at > review.stale_after:
        raise SubmissionExportError("review_stale")
    if now >= review.deadline:
        raise SubmissionExportError("deadline_passed")
    output_path = Path(output_path)
    if output_path.suffix.lower() != review.template_path.suffix.lower():
        raise SubmissionExportError("output_suffix_must_match_template")
    data: bytes = _guarded(lambda: _bounded_bytes(review.template_path, review._limits))
    template: _Template = _guarded(lambda: _read_template(data, review._limits))
    if template.digest != review.template_digest:
        raise SubmissionExportError("template_changed_since_review")
    expected = _Expected(review.participant, review.pairs, review.bank.kind,
                         review.players_digest, review._registry, review._provenance,
                         review._limits)
    output, changed = _guarded(lambda: _fill(data, template, review._edits))
    _verify(data, output, changed, expected)
    try:
        target = output_path.open("xb")
    except FileExistsError:
        raise SubmissionExportError("output_exists") from None
    except OSError:
        raise SubmissionExportError("output_not_writable") from None
    try:
        with target:
            target.write(output)
    except OSError:
        os.unlink(output_path)
        raise SubmissionExportError("output_not_writable") from None
    try:
        written: bytes = _guarded(lambda: _bounded_bytes(output_path, review._limits))
        if written != output:
            raise SubmissionExportError("output_changed_after_write")
        sheet = _verify(data, written, changed, expected)
    except SubmissionExportError:
        os.unlink(output_path)
        raise
    with ZipFile(BytesIO(written)) as archive:
        members = len(archive.infolist())
    return SubmissionExport(
        review=review, output_path=output_path,
        output_digest=hashlib.sha256(written).hexdigest(), exported_at=now,
        changed_members=changed, preserved_members=members - len(changed), reimported=sheet,
    )


def submitted_record(
    export: SubmissionExport, *, record_id: str, sent_at: datetime, evidence: Provenance,
) -> LedgerRecord:
    """Ledger record, for the reviewed entry, of a sheet its participant emailed themself.

    Call only with evidence that the exported file was actually sent. A
    ``Submitted`` record debits nothing and earns no bonus; replay counts it
    only after a separate ``Accepted`` record from the commissioner.
    """
    _aware(sent_at, "Send time")
    if sent_at < export.exported_at:
        raise ValueError("A sheet cannot be sent before it was exported")
    if sent_at >= export.review.deadline:
        raise ValueError("Sheet sent after the deadline cannot be a voluntary submission")
    return LedgerRecord(
        record_id=record_id, entry_id=export.review.entry_id, event_id=export.review.event_id,
        effective_at=sent_at, evidence=evidence,
        payload=Submitted(picks=export.pairs, submitted_at=sent_at, excel=True),
    )


__all__ = [
    "BankReview", "SlotReview", "SubmissionExport", "SubmissionExportError", "SubmissionReview",
    "SubmissionSheet", "export_submission", "read_submission", "review_submission",
    "submitted_record",
]

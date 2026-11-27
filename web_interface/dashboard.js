// Pool dashboard: one event decision in its season context.
// Talks only to the local typed routes. Every value is rendered with textContent
// (never as HTML markup), and private season data stays in memory: nothing is written
// to browser storage.

(() => {
    'use strict';

    const MESSAGES = {
        rules_unresolved: 'Strict mode: the 2026 rule interpretations are still provisional. Tick "Use provisional rule interpretations" to proceed with the recorded development assumptions.',
        deadline_passed: 'The deadline has passed: recommendations are disabled and the sheet cannot be re-selected. Monitoring only.',
        no_provider_loader: 'No calibrated provider loader is configured, so no scenarios can be simulated yet.',
        unknown_artifact: 'Choose a model artifact from the configured manifest.',
        pool_inputs_not_configured: 'TENNIS_POOL_ROOT is not configured.',
        season_input_missing: 'No season.json in the pool directory: season state is unavailable.',
        invalid_season_input: 'season.json failed validation or its ledger does not replay.',
        event_terms_missing: 'season.json has no terms (deadline) for this event.',
        objective_unavailable: 'That objective needs rival entries (and, for payout, a printed 40/60/80 schedule).',
        draw_event_mismatch: 'The imported draw belongs to another event.',
        rankings_missing: 'Every unseeded draw player needs first-day ranking evidence (upset bonuses order them by rank). Load the rankings JSON.',
        invalid_rankings: 'The rankings file is not a list of canonical ranking snapshots for draw players.',
        busy: 'Another job is running; try again in a moment.',
        job_timeout: 'The job hit its time limit; lower the simulations.',
    };
    const BANDS = ['1-4', '5-8', '9-16', '17-32'];

    const state = {
        status: null,
        draw: null,
        drawEvent: null,
        rankings: [],
        names: {},
        season: null,
        decision: null,
        previous: {},   // event_id -> last decision, for refresh impact
        locked: {},     // event_id -> locked pairs, compared on every refresh
        generation: 0,  // bumped on every event change; late responses for older ones are dropped
    };

    // The selected event and its generation, captured before any request.
    function selectionContext() { return { event: eventId(), generation: state.generation }; }

    function current(context) {
        return context.generation === state.generation && context.event === eventId();
    }

    // --- small DOM helpers ---------------------------------------------------

    function el(tag, attrs, ...children) {
        const node = document.createElement(tag);
        for (const [key, value] of Object.entries(attrs || {})) {
            if (key === 'class') node.className = value;
            else if (key === 'onclick') node.addEventListener('click', value);
            else node.setAttribute(key, value);
        }
        for (const child of children.flat()) {
            if (child === null || child === undefined || child === false) continue;
            node.append(child instanceof Node ? child : document.createTextNode(String(child)));
        }
        return node;
    }

    function $(id) { return document.getElementById(id); }

    function fill(id, ...children) {
        const node = $(id);
        node.replaceChildren(...children.flat().filter(c => c !== null && c !== undefined));
        return node;
    }

    function show(id, visible = true) { $(id).hidden = !visible; }

    function scroll(node) { return el('div', { class: 'dash-scroll' }, node); }

    function table(headers, rows) {
        return el('table', { class: 'dash-table' },
            el('thead', {}, el('tr', {}, headers.map(h => el('th', { scope: 'col' }, h)))),
            el('tbody', {}, rows.map(row => el('tr', {}, row.map(cell => el('td', {}, cell))))));
    }

    function num(value, digits = 1) {
        return value === null || value === undefined ? 'n/a' : Number(value).toFixed(digits);
    }

    function pct(value, digits = 1) {
        return value === null || value === undefined ? 'n/a' : `${(100 * value).toFixed(digits)}%`;
    }

    function money(cents) {
        return cents === null || cents === undefined ? 'n/a' : `$${(cents / 100).toFixed(2)}`;
    }

    function pm(value, se, fmt = num) {
        if (value === null || value === undefined) return 'n/a';
        return se === null || se === undefined ? fmt(value) : `${fmt(value)} ± ${fmt(se)}`;
    }

    function when(iso) {
        return iso ? new Date(iso).toLocaleString() : 'n/a';
    }

    function name(playerId) {
        return state.names[playerId] || playerId;
    }

    function selection(sel) {
        return sel ? `${name(sel.player_id)} [${sel.band}]` : 'none';
    }

    function setStatus(text, kind = 'info') {
        const node = $('dash-status');
        node.textContent = text;
        node.dataset.kind = kind;
    }

    function explain(code) {
        return MESSAGES[code] || `Refused: ${code}`;
    }

    async function call(path, options) {
        const response = await fetch(path, options);
        let data = null;
        try { data = await response.json(); } catch (error) { data = { error: 'invalid_response' }; }
        if (!response.ok) throw Object.assign(new Error(data.error || 'error'), { code: data.error });
        return data;
    }

    function postJson(path, body) {
        return call(path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(body) });
    }

    async function busy(button, work) {
        const context = selectionContext();
        button.disabled = true;
        try {
            await work();
        } catch (error) {
            if (current(context)) setStatus(explain(error.code || error.message), 'error');
        } finally {
            button.disabled = button.dataset.locked === 'true';
        }
    }

    // --- setup ---------------------------------------------------------------

    async function loadStatus() {
        try {
            state.status = await call('/api/status');
        } catch (error) {
            setStatus('Status unavailable.', 'error');
            return;
        }
        const events = state.status.pool_events || [];
        fill('dash-event', events.map(e => el('option', { value: e }, e.replaceAll('_', ' '))));
        const artifacts = state.status.artifacts || [];
        fill('dash-artifact', artifacts.length
            ? artifacts.map(a => el('option', { value: a }, a))
            : [el('option', { value: '' }, 'No artifact configured')]);
        if (!events.length) setStatus(explain('pool_inputs_not_configured'), 'warn');
        else if (!state.status.season_configured) setStatus(explain('season_input_missing'), 'warn');
        else if (!state.status.provider_kinds.length) setStatus(explain('no_provider_loader'), 'warn');
        else setStatus('Choose an event, import its draw, then load the season.');
    }

    function eventId() { return $('dash-event').value; }

    function provisional() { return $('dash-provisional').checked; }

    async function readRankings() {
        const file = $('dash-rankings').files[0];
        if (!file) { state.rankings = []; return; }
        let parsed;
        try { parsed = JSON.parse(await file.text()); } catch (error) { parsed = null; }
        if (!Array.isArray(parsed)) throw Object.assign(new Error('invalid_rankings'), { code: 'invalid_rankings' });
        state.rankings = parsed;
    }

    async function importDraw() {
        const file = $('dash-workbook').files[0];
        if (!file) { setStatus('Choose the event workbook first.', 'warn'); return; }
        const context = selectionContext();
        const suffix = file.name.toLowerCase().endsWith('.xlsm') ? '.xlsm' : '.xlsx';
        const query = new URLSearchParams({ event_id: context.event, format: $('dash-format').value, suffix });
        const data = await call(`/api/workbooks/preview?${query}`, {
            method: 'POST', headers: { 'Content-Type': 'application/octet-stream' },
            body: await file.arrayBuffer() });
        if (!current(context)) return;
        state.draw = data.draw;
        state.drawEvent = context.event;
        const players = data.draw.slots.filter(s => s.player_id).length;
        fill('dash-draw', el('div', { class: 'dash-note' },
            `Draw imported: ${data.draw.event.name}, ${players} players, ${data.rankings} ranked. `,
            `Upload ${data.upload_sha256.slice(0, 12)}…, registry ${data.registry_revision}.`),
            data.warnings.length || data.missing_sheets.length ? el('ul', { class: 'dash-warnings' },
                data.missing_sheets.map(s => el('li', {}, `Missing sheet: ${s}`)),
                data.warnings.map(w => el('li', {}, w))) : null);
        setStatus('Draw ready. Load the season or refresh the recommendation.');
    }

    // --- season state ----------------------------------------------------------

    function renderMode(view) {
        const banner = $('dash-mode');
        const decide = $('dash-decide');
        const locked = view.mode !== 'decision';
        decide.dataset.locked = String(locked);
        decide.disabled = locked;
        banner.dataset.mode = view.mode;
        if (locked) {
            banner.replaceChildren(el('strong', {}, 'Monitoring mode. '),
                `The deadline passed at ${when(view.deadline)}. Recommendations are disabled and `,
                'no sheet can be re-selected after lock; this view shows the accepted sheet and standings.');
        } else {
            const hours = (new Date(view.deadline) - new Date(view.now)) / 36e5;
            banner.replaceChildren(el('strong', {}, 'Decision mode. '),
                `Deadline ${when(view.deadline)} (${hours.toFixed(1)} h from the server clock). `,
                'You review and send the sheet yourself; this app never submits anything.');
        }
        show('dash-mode');
    }

    function renderSeason(view) {
        Object.assign(state.names, view.names || {});
        state.season = view;
        renderMode(view);
        const own = view.own;
        fill('dash-own',
            el('p', {}, `${own.bank_kind === 'slam' ? 'Slam' : 'Masters'} bank for this event, `,
                `season points ${own.season_points} (bonus ${own.submission_bonus}), `,
                `${own.qualifying_events}/7 qualifying Excel sheets.`,
                own.in_ledger ? '' : ' Not in the ledger yet: full bank assumed.'),
            table(['Band', 'Tokens left'], own.bank.map(b => [b.band, b.remaining])),
            own.usage.length
                ? table(['Player', 'Uses', 'Uses left'],
                    own.usage.map(u => [name(u.player_id), u.uses, u.remaining]))
                : el('p', { class: 'dash-note' }, 'No player uses yet.'));
        fill('dash-standings', el('h4', {}, 'Standings and gaps'),
            scroll(table(['Rank', 'Entry', 'Season points', 'Your gap', 'Qualifying sheets'],
                view.standings.map(s => [s.rank, s.own ? `${s.entry_id} (you)` : s.entry_id,
                    s.season_points, s.own ? '–' : (s.gap > 0 ? `+${s.gap}` : s.gap),
                    s.qualifying_events]))));
        fill('dash-calendar', el('h4', {}, 'Calendar'),
            table(['Event', 'Deadline', 'Status', 'Your sheet accepted'],
                view.calendar.map(c => [c.event_id.replaceAll('_', ' '), when(c.deadline),
                    c.status, c.accepted ? 'yes' : 'no'])));
        const event = view.event;
        fill('dash-event-state',
            el('p', {}, `Submitted records: ${event.submitted}. Accepted: ${event.accepted ? 'yes' : 'no'}. `,
                `Points recorded: ${event.points_recorded ? event.season_points : 'not yet'}.`),
            event.accepted_picks.length
                ? table(['Slot', 'Primary', 'Substitute'], event.accepted_picks.map(
                    (p, i) => [i + 1, selection(p.primary), selection(p.substitute)]))
                : el('p', { class: 'dash-note' }, 'No accepted sheet for this event in the ledger.'),
            view.mode !== 'decision' && event.selections.length
                ? el('p', {}, 'Scoring selections after activations: ',
                    event.selections.map(selection).join(', '))
                : null);
        show('dash-season-panel');
        show('dash-event-panel');
    }

    async function loadSeason() {
        const context = selectionContext();
        const view = await postJson('/api/pool/season',
            { event_id: context.event, allow_provisional: provisional() });
        if (!current(context)) return;
        renderSeason(view);
        setStatus(view.mode === 'decision'
            ? 'Season loaded. Refresh the recommendation when the draw is imported.'
            : explain('deadline_passed'), view.mode === 'decision' ? 'info' : 'warn');
    }

    // --- decision ------------------------------------------------------------

    function playerStats(result) {
        return Object.fromEntries(result.players.map(p => [p.player_id, p]));
    }

    function ownership(result) {
        const rows = result.rivals ? result.rivals.ownership : [];
        return Object.fromEntries(rows.map(o => [o.player_id, o]));
    }

    function ownershipText(own) {
        if (!own) return 'no rival field';
        return `${own.known} known · ${pct(own.expected, 0)} (${pct(own.low, 0)}–${pct(own.high, 0)})`;
    }

    function lockButton(event, pairs, label) {
        return el('button', { class: 'dash-small', type: 'button', onclick: () => {
            state.locked[event] = pairs;
            setStatus('Sheet locked for comparison. The next refresh scores it on the same scenarios.');
            renderCompare(state.decision);
        } }, label);
    }

    function renderMetrics(rec) {
        const m = rec.best.metrics;
        const search = rec.search;
        return el('div', { class: 'dash-metrics' },
            el('div', { class: 'dash-metric' }, el('span', {}, 'Expected points'), el('b', {}, pm(m.expected_points, m.points_se))),
            el('div', { class: 'dash-metric' }, el('span', {}, `Downside (worst ${pct(search.limits.robust_alpha, 0)} mean)`), el('b', {}, num(m.robust_points))),
            el('div', { class: 'dash-metric' }, el('span', {}, 'P(top-3) this event'), el('b', {}, pm(m.p_top3, m.p_top3_se, pct))),
            el('div', { class: 'dash-metric' }, el('span', {}, 'Expected event payout'), el('b', {}, pm(m.expected_payout_cents, m.payout_se_cents, money))),
            el('p', { class: 'dash-note' },
                `Objective: ${rec.assumptions.objective_definition} Search: ${search.method}, `,
                search.exhaustive ? 'exhaustive (optimum on these scenarios). '
                    : `heuristic, gap ${search.optimality_gap === null ? 'not measured' : num(search.optimality_gap, 2)} (${search.gap_basis}). `,
                `Tie rule: ${rec.assumptions.tie_rule}`));
    }

    function renderPairs(result) {
        const rec = result.recommendation;
        const stats = playerStats(result);
        const owned = ownership(result);
        const rows = rec.best.pairs.map((pair, i) => {
            const p = stats[pair.primary.player_id] || {};
            const risk = p.withdrawn_share
                ? `withdraws before playing (${pct(p.withdrawn_share)} of scenarios)`
                : 'withdraws before playing (no withdrawal risk was modelled for him)';
            const why = pair.substitute
                ? `If ${name(pair.primary.player_id)} ${risk}, ${name(pair.substitute.player_id)} takes the slot; an unused substitute costs nothing.`
                : `No substitute: if ${name(pair.primary.player_id)} ${risk}, the slot scores zero.`;
            return [i + 1, selection(pair.primary), `${num(p.mean_points)} / ${num(p.p90_points)}`,
                ownershipText(owned[pair.primary.player_id]), selection(pair.substitute), why];
        });
        return [table(['Slot', 'Primary', 'Mean / P90 pts', 'Rival ownership (known · projected)',
                       'Substitute', 'Why this pair'], rows),
                el('div', { class: 'dash-actions' },
                    lockButton(result.event_id, rec.best.pairs, 'Lock this sheet'))];
    }

    function meanOwnership(owned, pairs) {
        if (!Object.keys(owned).length) return 'n/a';
        const shares = pairs.map(p => (owned[p.primary.player_id] || { expected: 0 }).expected);
        return pct(shares.reduce((a, b) => a + b, 0) / shares.length);
    }

    function renderAlternatives(result) {
        const rec = result.recommendation;
        const owned = ownership(result);
        if (!rec.alternatives.length) return el('p', { class: 'dash-note' }, 'No alternatives returned.');
        return [el('h4', {}, 'Alternatives and near-ties'),
            el('p', { class: 'dash-note' },
                'A near-tie is within the noise of the simulation (paired shortfall within two standard errors; 1.5 points of P(top-3)). Prefer the lower-ownership option between ties.'),
            table(['#', 'Primaries', 'Mean projected ownership', 'Expected pts', 'P(top-3)', 'Gap to best', 'Verdict', ''],
                rec.alternatives.map((c, i) => [i + 1,
                    c.pairs.map(p => name(p.primary.player_id)).join(', '),
                    meanOwnership(owned, c.pairs),
                    pm(c.metrics.expected_points, c.metrics.points_se),
                    pm(c.metrics.p_top3, c.metrics.p_top3_se, pct),
                    pm(c.gap_to_best, c.gap_se, v => num(v, 2)),
                    c.tie_with_best ? 'near-tie' : 'worse',
                    lockButton(result.event_id, c.pairs, 'Lock')]))];
    }

    function renderCompare(result) {
        const locked = result && state.locked[result.event_id];
        if (!locked) { show('dash-compare-panel', Boolean(result && state.previous[result.event_id])); fill('dash-compare'); return; }
        const compare = result.compare;
        const sameSheet = compare && JSON.stringify(compare.pairs) === JSON.stringify(locked);
        fill('dash-compare',
            el('p', {}, 'Locked sheet: ', locked.map(p => selection(p.primary)).join(', '), ' ',
                el('button', { class: 'dash-small', type: 'button', onclick: () => {
                    delete state.locked[result.event_id]; renderCompare(result);
                } }, 'Unlock')),
            sameSheet && !compare.scorable ? [
                el('p', {}, 'Stale: a player in the locked sheet is no longer in the draw, so it cannot be scored. Unlock it or lock a new sheet.'),
                compare.problems.length ? el('ul', { class: 'dash-warnings' }, compare.problems.map(p => el('li', {}, p))) : null,
            ] : sameSheet ? [
                el('p', {}, compare.legal ? 'Legal against the season state before this event.'
                    : 'Not legal against the season state before this event.'),
                compare.problems.length ? el('ul', { class: 'dash-warnings' }, compare.problems.map(p => el('li', {}, p))) : null,
                table(['', 'Expected pts', 'Downside', 'P(top-3)', 'Payout'], [
                    ['Locked', pm(compare.metrics.expected_points, compare.metrics.points_se),
                        num(compare.metrics.robust_points), pct(compare.metrics.p_top3), money(compare.metrics.expected_payout_cents)],
                    ['Difference vs recommended', num(compare.expected_points_vs_best, 2),
                        num(compare.robust_points_vs_best, 2), '', ''],
                ]),
                el('p', { class: 'dash-note' }, compare.same_as_best ? 'The locked sheet is the current recommendation.'
                    : `Differences under about ${num(2 * compare.points_se, 1)} points are within simulation noise.`),
            ] : el('p', { class: 'dash-note' }, 'Refresh to score the locked sheet on the latest scenarios.'));
        show('dash-compare-panel');
    }

    function renderImpact(result, previous) {
        if (!previous) { fill('dash-impact'); return; }
        const before = new Set(previous.recommendation.best.pairs.map(p => p.primary.player_id));
        const after = new Set(result.recommendation.best.pairs.map(p => p.primary.player_id));
        const added = [...after].filter(p => !before.has(p)).map(name);
        const removed = [...before].filter(p => !after.has(p)).map(name);
        const was = previous.recommendation.best.metrics;
        const now = result.recommendation.best.metrics;
        const changes = [
            ['Information cutoff', `${when(previous.cutoff)} → ${when(result.cutoff)}`],
            ['Scenarios', previous.versions.scenario_digest === result.versions.scenario_digest ? 'unchanged' : 'changed'],
            ['Artifact', previous.versions.artifact_sha256 === result.versions.artifact_sha256 ? 'unchanged' : `${previous.versions.artifact} → ${result.versions.artifact}`],
            ['Objective', `${previous.recommendation.objective} → ${result.recommendation.objective}`],
            ['Primaries in', added.length ? added.join(', ') : 'none'],
            ['Primaries out', removed.length ? removed.join(', ') : 'none'],
            ['Expected points', `${num(was.expected_points)} → ${num(now.expected_points)}`],
            ['P(top-3)', `${pct(was.p_top3)} → ${pct(now.p_top3)}`],
        ];
        fill('dash-impact', el('h4', {}, 'Refresh impact (versus the previous refresh)'),
            table(['What', 'Change'], changes));
        show('dash-compare-panel');
    }

    function renderRivals(result) {
        const report = result.rivals;
        if (!report) {
            fill('dash-rivals', el('p', { class: 'dash-note' }, 'No rival entries in the season inputs.'));
            fill('dash-ownership');
            return;
        }
        const order = { known: 0, partial: 1, estimated: 2, no_history: 3 };
        const label = { known: 'exact (all five known)', partial: 'partly known', estimated: 'estimated from history', no_history: 'estimated, no history' };
        fill('dash-rivals',
            el('p', { class: 'dash-note' }, `Picks count as known only if available before ${when(report.visible_before)}. `,
                `${report.known_picks_used} known pairs used; ${report.excluded_after_cutoff + report.excluded_at_or_after_start} excluded by timing. `,
                `Appeal: ${report.appeal_basis}. Model parameters are unfitted priors.`),
            scroll(table(['Entry', 'Picks', 'Known pairs', 'History', 'Pick certainty', 'Bank before event'],
                [...report.rivals].sort((a, b) => order[a.status] - order[b.status]).map(r => [r.entry_id, label[r.status] || r.status, r.known_pairs,
                    r.history_events, num(r.pick_certainty, 2),
                    r.ledger_state ? r.bank.join('/') : 'not in ledger (full bank assumed)']))));
        const top = [...report.ownership].sort((a, b) => b.expected - a.expected).slice(0, 20);
        fill('dash-ownership', el('h4', {}, 'Projected ownership (top 20)'),
            scroll(table(['Player', 'Band', 'Known holders', `Projected (${pct(report.parameters.interval, 0)} interval)`],
                top.map(o => [name(o.player_id), o.band, o.known,
                    `${pct(o.expected)} (${pct(o.low)}–${pct(o.high)})`]))));
    }

    function renderPlan(result) {
        const plan = result.plan;
        if (!plan) {
            fill('dash-plan', el('p', { class: 'dash-note' },
                'No season plan: prospects for later events are missing in season.json, so there is no preservation advice. This event was optimized alone.'));
            return;
        }
        const chosen = plan.projections.find(p => p.policy === plan.chosen);
        fill('dash-plan',
            el('p', {}, `Chosen policy: ${plan.chosen} (season objective ${plan.objective}). `,
                'Policies within two paired standard errors tie; a tie spends fewer tokens now.'),
            table(['Policy', 'Season pts', 'This event', 'Later', 'Unused tokens', 'P(season top-3)', 'Season payout', 'Verdict'],
                plan.projections.map(p => [p.policy, pm(p.season_expected_points, p.season_points_se),
                    num(p.event_expected_points), num(p.future_expected_points), num(p.expected_unused_tokens, 2),
                    pct(p.p_season_top3), pm(p.expected_season_payout_cents, p.season_payout_se_cents, money),
                    p.policy === plan.chosen ? 'chosen' : (p.tie_with_best ? 'tie' : `gap ${pm(p.gap_to_best, p.gap_se)}`)])),
            chosen && chosen.rival_gaps.length ? [el('h4', {}, 'Gaps to nearby rivals'),
                table(['Entry', 'Gap now', 'Expected final gap', 'P(finish ahead)'],
                    chosen.rival_gaps.map(g => [g.entry_id, g.current_gap,
                        pm(g.expected_final_gap, g.final_gap_se), pct(g.p_finish_ahead)]))] : null,
            chosen && chosen.notes.length ? el('ul', { class: 'dash-warnings' }, chosen.notes.map(n => el('li', {}, n))) : null,
            el('h4', {}, 'Band tokens: now versus later'),
            table(['Bank', 'Band', 'Left', 'Planned', 'Gain now', 'Value later', 'Advice', 'Why'],
                plan.token_costs.map(c => [c.bank, c.band, c.remaining, c.planned_spend, num(c.gain_now),
                    pm(c.value_later, c.value_later_se), c.advice, c.explanation])),
            el('h4', {}, 'Player uses: spend or preserve'),
            table(['Player', 'Uses left', 'In plan', 'Edge now', 'Value later', 'Advice', 'Why'],
                plan.use_costs.map(c => [name(c.player_id), c.uses_left, c.in_plan ? 'yes' : 'no',
                    num(c.edge_now), pm(c.value_later, c.value_later_se), c.advice, c.explanation])));
    }

    function renderVersions(result) {
        const v = result.versions;
        const provider = result.provider;
        const provisional = v.rules.decisions.filter(d => d.status !== 'resolved').length;
        const tally = rows => rows.length ? rows.map(r => `${r.value} (${r.count})`).join(', ') : 'none';
        fill('dash-versions',
            el('p', { class: 'dash-notice' }, result.notice),
            table(['Item', 'Value'], [
                ['Server clock', when(result.now)],
                ['Information cutoff', when(result.cutoff)],
                ['Latest prediction cutoff', when(provider.latest_prediction_cutoff)],
                ['Deadline', when(result.deadline)],
                ['Tournament start (later of start date 00:00 UTC and deadline)', when(result.starts_at)],
                ['Model artifact', `${v.artifact} (sha256 ${v.artifact_sha256.slice(0, 16)}…)`],
                ['Model versions', tally(provider.model_versions)],
                ['Calibration (per prediction)', tally(provider.calibration_versions)],
                ['Scenarios', `${v.scenarios.simulations} runs, seed ${v.scenarios.seed}, digest ${v.scenario_digest.slice(0, 16)}…`],
                ['Withdrawal model', `${v.scenarios.withdrawal_model}; ${v.scenarios.withdrawal_probabilities.length} listed players`],
                ['Rule register', `${v.rules.register_version}; ${provisional} provisional decisions`],
                ['Ledger history', `${v.ledger_history_digest.slice(0, 16)}…`],
                ['Draw source', `${v.draw_provenance.source} ${v.draw_provenance.source_version}`],
                ['First-day ranking snapshots', v.ranking_snapshots],
                ['Missing provider coverage', tally(provider.missing_coverage)],
                ['Provider warnings', tally(provider.warnings)],
            ]),
            el('h4', {}, 'Coverage warnings'),
            el('ul', { class: 'dash-warnings' }, result.coverage_warnings.map(w => el('li', {}, w))));
    }

    function renderDecision(result) {
        Object.assign(state.names, result.names || {});
        const previous = state.previous[result.event_id];
        state.decision = result;
        renderSeason({ ...result.season, names: result.names });
        fill('dash-metrics', renderMetrics(result.recommendation));
        fill('dash-pairs', renderPairs(result));
        fill('dash-alternatives', renderAlternatives(result));
        renderCompare(result);
        renderImpact(result, previous);
        renderRivals(result);
        renderPlan(result);
        renderVersions(result);
        state.previous[result.event_id] = result;
        ['dash-recommendation-panel', 'dash-rivals-panel', 'dash-plan-panel', 'dash-versions-panel']
            .forEach(id => show(id));
    }

    async function decide() {
        if (!state.draw || state.drawEvent !== eventId()) {
            setStatus('Import this event\'s draw first.', 'warn');
            return;
        }
        const context = selectionContext();
        await readRankings();
        setStatus('Simulating scenarios, rival sheets and the season plan…');
        const body = {
            event_id: context.event, artifact: $('dash-artifact').value, draw: state.draw,
            simulations: Number($('dash-simulations').value), seed: Number($('dash-seed').value),
            objective: $('dash-objective').value, season_objective: $('dash-season-objective').value,
            allow_provisional: provisional(), rankings: state.rankings,
        };
        if (state.locked[context.event]) body.compare = state.locked[context.event];
        try {
            const result = await postJson('/api/pool/decision', body);
            if (!current(context)) return;
            renderDecision(result);
            setStatus('Recommendation refreshed. Review it, then send your sheet yourself.');
        } catch (error) {
            if (!current(context)) return;
            if (error.code === 'deadline_passed') await loadSeason().catch(() => {});
            throw error;
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        if (!$('pool-dashboard')) return;
        $('dash-preview').addEventListener('click', e => busy(e.currentTarget, importDraw));
        $('dash-season').addEventListener('click', e => busy(e.currentTarget, loadSeason));
        $('dash-decide').addEventListener('click', e => busy(e.currentTarget, decide));
        $('dash-event').addEventListener('change', () => {
            // Results belong to one event: drop the active ones, keep per-event history and locks.
            state.generation += 1;
            state.decision = null;
            state.draw = null;
            state.drawEvent = null;
            fill('dash-draw');
            ['dash-season-panel', 'dash-event-panel', 'dash-recommendation-panel',
             'dash-compare-panel', 'dash-rivals-panel', 'dash-plan-panel', 'dash-versions-panel']
                .forEach(id => show(id, false));
            $('dash-decide').dataset.locked = 'false';
            $('dash-decide').disabled = false;
            show('dash-mode', false);
            setStatus('Event changed: import its draw and load the season.');
        });
        loadStatus();
    });
})();

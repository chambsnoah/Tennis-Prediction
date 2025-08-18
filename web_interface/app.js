// Tennis Prediction System - Frontend JavaScript
// Handles all user interactions and API calls

class TennisPredictionApp {
    constructor() {
        this.currentTournament = null;
        this.currentGender = 'female';
        this.players = [];
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadTournaments();
        this.showTab('match-prediction');
    }

    setupEventListeners() {
        // Tab navigation
        document.querySelectorAll('.nav-tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                const tabId = e.currentTarget.dataset.tab;
                this.showTab(tabId);
            });
        });

        // Match prediction events
        document.getElementById('simulate-match').addEventListener('click', () => {
            this.simulateMatch();
        });

        // Player selection events
        document.getElementById('player1-select').addEventListener('change', (e) => {
            this.updatePlayerStats('player1-stats', e.target.value);
        });

        document.getElementById('player2-select').addEventListener('change', (e) => {
            this.updatePlayerStats('player2-stats', e.target.value);
        });

        // Tournament selection events
        document.getElementById('tournament-select').addEventListener('change', (e) => {
            this.loadTournamentData(e.target.value);
        });

        document.getElementById('gender-select').addEventListener('change', (e) => {
            this.currentGender = e.target.value;
            this.loadTournamentData(this.currentTournament);
        });

        // Optimization events
        document.getElementById('opt-tournament').addEventListener('change', (e) => {
            this.currentTournament = e.target.value;
        });

        document.getElementById('opt-gender').addEventListener('change', (e) => {
            this.currentGender = e.target.value;
        });

        document.getElementById('run-optimization').addEventListener('click', () => {
            this.runOptimization();
        });

        // Player search
        document.getElementById('player-search').addEventListener('input', (e) => {
            this.searchPlayers(e.target.value);
        });
    }

    showTab(tabId) {
        // Hide all tabs
        document.querySelectorAll('.tab-content').forEach(tab => {
            tab.classList.remove('active');
        });

        document.querySelectorAll('.nav-tab').forEach(tab => {
            tab.classList.remove('active');
        });

        // Show selected tab
        document.getElementById(tabId).classList.add('active');
        document.querySelector(`[data-tab="${tabId}"]`).classList.add('active');

        // Load data for specific tabs
        if (tabId === 'bracket-view') {
            this.loadBracket();
        }
    }

    showLoading(show = true) {
        const overlay = document.getElementById('loading-overlay');
        if (show) {
            overlay.classList.add('show');
        } else {
            overlay.classList.remove('show');
        }
    }

    async loadTournaments() {
        try {
            const response = await fetch('/api/tournaments');
            const tournaments = await response.json();

            // Populate tournament selectors
            const selectors = ['tournament-select', 'opt-tournament'];
            selectors.forEach(selectorId => {
                const select = document.getElementById(selectorId);
                select.innerHTML = '<option value="">Select Tournament</option>';
                
                tournaments.forEach(tournament => {
                    const option = document.createElement('option');
                    option.value = tournament.id;
                    option.textContent = tournament.name;
                    select.appendChild(option);
                });
            });

            // Load first tournament by default
            if (tournaments.length > 0) {
                this.currentTournament = tournaments[0].id;
                document.getElementById('tournament-select').value = this.currentTournament;
                document.getElementById('opt-tournament').value = this.currentTournament;
                this.loadTournamentData(this.currentTournament);
            }

        } catch (error) {
            console.error('Error loading tournaments:', error);
            this.showError('Failed to load tournaments');
        }
    }

    async loadTournamentData(tournamentId) {
        if (!tournamentId) return;

        this.currentTournament = tournamentId;
        this.showLoading(true);

        try {
            const response = await fetch(`/api/players/${tournamentId}/${this.currentGender}`);
            const players = await response.json();

            if (response.ok) {
                this.players = players;
                this.populatePlayerSelectors();
            } else {
                this.showError(players.error || 'Failed to load players');
            }

        } catch (error) {
            console.error('Error loading tournament data:', error);
            this.showError('Failed to load tournament data');
        } finally {
            this.showLoading(false);
        }
    }

    populatePlayerSelectors() {
        const selectors = ['player1-select', 'player2-select'];
        
        selectors.forEach(selectorId => {
            const select = document.getElementById(selectorId);
            select.innerHTML = '<option value="">Select Player</option>';
            
        this.players.forEach(player => {
            const option = document.createElement('option');
            option.value = player.name;
            option.textContent = `${player.name} (${player.seed})`;
            select.appendChild(option);
        });
        });

        // Clear previous stats
        document.getElementById('player1-stats').innerHTML = '';
        document.getElementById('player2-stats').innerHTML = '';
    }

    updatePlayerStats(statsElementId, playerName) {
        const statsElement = document.getElementById(statsElementId);
        
        if (!playerName) {
            statsElement.innerHTML = '';
            return;
        }

        const player = this.players.find(p => p.name === playerName);
        if (!player) return;

        statsElement.innerHTML = `
            <div class="stat-item">
                <span class="stat-label">Seed:</span>
                <span class="stat-value">#${player.seed}</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Cost:</span>
                <span class="stat-value">$${player.cost.toLocaleString()}</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">P-Factor:</span>
                <span class="stat-value">${(player.p_factor * 100).toFixed(1)}%</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">N-Factor:</span>
                <span class="stat-value">${(player.n_factor * 100).toFixed(1)}%</span>
            </div>
        `;
    }

    async simulateMatch() {
        const player1Name = document.getElementById('player1-select').value;
        const player2Name = document.getElementById('player2-select').value;
        const setsToWin = parseInt(document.getElementById('sets-to-win').value);
        const numSimulations = parseInt(document.getElementById('simulation-count').value);
        const surface = document.getElementById('tournament-surface').value;

        if (!player1Name || !player2Name) {
            this.showError('Please select both players');
            return;
        }

        if (player1Name === player2Name) {
            this.showError('Please select different players');
            return;
        }

        this.showLoading(true);

        try {
            const response = await fetch('/api/simulate-match', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    tournament_path: this.currentTournament,
                    gender: this.currentGender,
                    player1_name: player1Name,
                    player2_name: player2Name,
                    sets_to_win: setsToWin,
                    num_simulations: numSimulations,
                    surface: surface
                })
            });

            const results = await response.json();

            if (response.ok) {
                this.displayMatchResults(results, player1Name, player2Name);
            } else {
                this.showError(results.error || 'Simulation failed');
            }

        } catch (error) {
            console.error('Error simulating match:', error);
            this.showError('Failed to simulate match');
        } finally {
            this.showLoading(false);
        }
    }

    displayMatchResults(results, player1Name, player2Name) {
        // Show results section
        document.getElementById('match-results').style.display = 'block';

        // Update probability bar
        const probFill = document.getElementById('prob-fill');
        const player1Prob = document.getElementById('player1-prob');
        const player2Prob = document.getElementById('player2-prob');

        probFill.style.width = `${results.player1_win_percentage}%`;
        player1Prob.textContent = `${results.player1_win_percentage}%`;
        player2Prob.textContent = `${results.player2_win_percentage}%`;

        // Update player names in results
        document.getElementById('p1-name').textContent = player1Name;
        document.getElementById('p2-name').textContent = player2Name;
        document.getElementById('detailed-p1-name').textContent = player1Name;
        document.getElementById('detailed-p2-name').textContent = player2Name;

        // Update match statistics
        document.getElementById('p1-wins').textContent = results.player1_wins;
        document.getElementById('p2-wins').textContent = results.player2_wins;
        document.getElementById('p1-avg-points').textContent = `${results.player1_avg_points}`;
        document.getElementById('p2-avg-points').textContent = `${results.player2_avg_points}`;
        document.getElementById('p1-avg-sets').textContent = results.player1_avg_sets;
        document.getElementById('p2-avg-sets').textContent = results.player2_avg_sets;

        // Update detailed statistics table
        const detailedStatsBody = document.getElementById('detailed-stats-body');
        detailedStatsBody.innerHTML = `
            <tr>
                <td>Total Points Won</td>
                <td>${results.player1_total_points}</td>
                <td>${results.player2_total_points}</td>
            </tr>
            <tr>
                <td>Average Points per Match</td>
                <td>${results.player1_avg_points}</td>
                <td>${results.player2_avg_points}</td>
            </tr>
            <tr>
                <td>Total Sets Won</td>
                <td>${results.player1_total_sets}</td>
                <td>${results.player2_total_sets}</td>
            </tr>
            <tr>
                <td>Average Sets per Match</td>
                <td>${results.player1_avg_sets}</td>
                <td>${results.player2_avg_sets}</td>
            </tr>
            <tr>
                <td>Win Percentage</td>
                <td>${results.player1_win_percentage}%</td>
                <td>${results.player2_win_percentage}%</td>
            </tr>
        `;

        // Scroll to results
        document.getElementById('match-results').scrollIntoView({ behavior: 'smooth' });
    }

    async loadBracket() {
        if (!this.currentTournament) return;

        this.showLoading(true);

        try {
            const response = await fetch(`/api/bracket/${this.currentTournament}/${this.currentGender}`);
            const bracketData = await response.json();

            if (response.ok) {
                this.displayBracket(bracketData);
            } else {
                this.showError(bracketData.error || 'Failed to load bracket');
            }

        } catch (error) {
            console.error('Error loading bracket:', error);
            this.showError('Failed to load bracket');
        } finally {
            this.showLoading(false);
        }
    }

    displayBracket(bracketData) {
        const bracketDisplay = document.getElementById('bracket-display');
        
        if (bracketData.matches && bracketData.matches.length > 0) {
            bracketDisplay.innerHTML = bracketData.matches.map(match => `
                <div class="bracket-match">
                    <div class="match-players">
                        <div class="player-name">${match.player1}</div>
                        <div class="player-name">${match.player2}</div>
                    </div>
                    <div class="match-info">
                        <span class="match-round">${match.round}</span>
                        <span class="match-status">${match.status}</span>
                    </div>
                </div>
            `).join('');
        } else {
            // Fallback to raw text display
            bracketDisplay.innerHTML = `
                <div class="bracket-text">
                    <pre>${bracketData.bracket_text || 'No bracket data available'}</pre>
                </div>
            `;
        }
    }

    searchPlayers(query) {
        const searchResults = document.getElementById('search-results');
        
        if (!query || query.length < 2) {
            searchResults.style.display = 'none';
            return;
        }

        const filteredPlayers = this.players.filter(player => 
            player.name.toLowerCase().includes(query.toLowerCase())
        );

        if (filteredPlayers.length > 0) {
            searchResults.innerHTML = filteredPlayers.slice(0, 10).map(player => `
                <div class="search-result" data-player-name="${player.name}">
                    ${player.name} (Seed #${player.seed})
                </div>
            `).join('');

            // Add click handlers
            searchResults.querySelectorAll('.search-result').forEach(result => {
                result.addEventListener('click', (e) => {
                    const playerName = e.target.dataset.playerName;
                    this.showPlayerProfile(playerName);
                    searchResults.style.display = 'none';
                    document.getElementById('player-search').value = '';
                });
            });

            searchResults.style.display = 'block';
        } else {
            searchResults.style.display = 'none';
        }
    }

    showPlayerProfile(playerName) {
        const player = this.players.find(p => p.name === playerName);
        if (!player) return;

        const profileElement = document.getElementById('player-profile');
        
        // Update profile header
        document.getElementById('profile-name').textContent = player.name;
        document.getElementById('profile-seed').textContent = `Seed #${player.seed}`;
        document.getElementById('profile-cost').textContent = `$${player.cost.toLocaleString()}`;

        // Update performance factors
        const pFactorBar = document.getElementById('p-factor-bar');
        const nFactorBar = document.getElementById('n-factor-bar');
        const pFactorValue = document.getElementById('p-factor-value');
        const nFactorValue = document.getElementById('n-factor-value');

        const pFactorPercent = player.p_factor * 100;
        const nFactorPercent = player.n_factor * 100;

        pFactorBar.style.width = `${Math.min(pFactorPercent * 10, 100)}%`;
        nFactorBar.style.width = `${Math.min(nFactorPercent * 10, 100)}%`;
        pFactorValue.textContent = `${pFactorPercent.toFixed(1)}%`;
        nFactorValue.textContent = `${nFactorPercent.toFixed(1)}%`;

        profileElement.style.display = 'block';
    }

    async runOptimization() {
        const budget = parseInt(document.getElementById('budget').value);
        const teamSize = parseInt(document.getElementById('team-size').value);

        if (!this.currentTournament) {
            this.showError('Please select a tournament');
            return;
        }

        this.showLoading(true);

        try {
            const response = await fetch('/api/optimize-team', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    tournament_path: this.currentTournament,
                    gender: this.currentGender,
                    budget: budget,
                    team_size: teamSize
                })
            });

            const results = await response.json();

            if (response.ok) {
                this.displayOptimizationResults(results);
            } else {
                this.showError(results.error || 'Optimization failed');
            }

        } catch (error) {
            console.error('Error running optimization:', error);
            this.showError('Failed to run optimization');
        } finally {
            this.showLoading(false);
        }
    }

    displayOptimizationResults(results) {
        // Show results section
        document.getElementById('optimization-results').style.display = 'block';

        // Update summary statistics
        document.getElementById('total-score').textContent = results.total_score;
        document.getElementById('total-cost').textContent = `$${results.total_cost.toLocaleString()}`;
        document.getElementById('budget-used').textContent = `${results.budget_used}%`;

        // Update team roster
        const rosterGrid = document.getElementById('roster-grid');
        rosterGrid.innerHTML = results.team_roster.map(player => `
            <div class="roster-player">
                <div class="roster-player-name">${player.name}</div>
                <div class="roster-player-details">
                    <span>Seed #${player.seed}</span>
                    <span>$${player.cost.toLocaleString()}</span>
                </div>
                <div class="roster-player-details">
                    <span>${player.points} pts</span>
                    <span>P: ${(player.p_factor * 100).toFixed(1)}%</span>
                </div>
            </div>
        `).join('');

        // Scroll to results
        document.getElementById('optimization-results').scrollIntoView({ behavior: 'smooth' });
    }

    showError(message) {
        // Simple error display - in a real app you'd want a proper notification system
        alert(`Error: ${message}`);
    }
}

// Initialize the app when the page loads
document.addEventListener('DOMContentLoaded', () => {
    new TennisPredictionApp();
});

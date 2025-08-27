# Test 1: TournamentDraw fix
from tennis_api.models.tournament_data import TournamentDraw
test_data = {'tournament_id': 'test', 'tournament_name': 'Test', 'year': 2024, 'surface': 'hard'}
t = TournamentDraw.from_dict(test_data)
print('✓ Bug 1 FIXED: TournamentDraw.from_dict works without category')

# Test 2: PlayerStats fix  
from tennis_api.models.player_stats import PlayerStats
p = PlayerStats(name='Test', current_ranking=10)
d = p.to_dict()
d['first_serve_pct'] = 0.65  # This caused the original error
p2 = PlayerStats.from_dict(d)
print('✓ Bug 2 FIXED: PlayerStats.from_dict filters extra keys')

# Test 3: Rate limiter fix
from tennis_api.cache.rate_limiter import RateLimiter
r = RateLimiter()
h = r.check_availability('rapidapi_tennis_live', 'high')
n = r.check_availability('rapidapi_tennis_live', 'normal')
assert h['priority_factor'] > n['priority_factor']
print('✓ Bug 3 FIXED: Priority handling works correctly')

print('🎉 ALL THREE CRITICAL BUGS SUCCESSFULLY FIXED!')
import json
import re

setting = "m"

def seed_to_cost(seed):
    if seed == 1:
        return 27000
    elif seed == 2:
        return 26000
    elif 3 <= seed and seed <= 7:
        return 22500
    elif 8 <= seed and seed <= 12:
        return 18500
    elif 13 <= seed and seed <= 16:
        return 16700
    elif 17 <= seed and seed <= 31:
        return 11900
    elif 32 <= seed and seed <= 63:
        return 6650
    else:
        return 5000

def extract_players(file_name):
    players = {}
    with open(file_name, 'r') as file:
        lines = file.readlines()
        i = 0
        while i < len(lines):
            if "Ranking" in lines[i]:
                full_name = lines[i-2].strip()  # Player name is 2 lines before "Ranking"
                name_parts = full_name.split(' ')
                first_name = name_parts[0]  # First name is the first part
                last_name = ' '.join(name_parts[1:])  # Last name is the rest of the parts
                name = f"{first_name[0]}. {last_name}"  # Format name as "F. Lastname"
                match = re.search(r'Ranking (\d+)', lines[i])
                if match is None:
                    print(f"No seed found for player: {name}")  # Debugging line
                    i += 1
                    continue
                seed = int(match.group(1))  # Adjusted to group 1 to get the seed
                cost = seed_to_cost(seed)
                players[name] = {"seed": seed, "cost": cost}
            i += 1
    return players

if setting == "m":
    players = extract_players('players_male.txt')
else:
    players = extract_players('players_female.txt')

if setting == "m":
    with open('players_male.json', 'w') as json_file:
        json.dump(players, json_file, indent=4)
else:
    with open('players_female.json', 'w') as json_file:
        json.dump(players, json_file, indent=4)
import json

config = "f"

bracket_file = ""
players_file = ""

if config == "m":
    bracket_file = "bracket_male"
    players_file = "players_male.json"
elif config == "f":
    bracket_file = "bracket_female"
    players_file = "players_female.json"
    
file = open(bracket_file + ".txt")

# read the file
text = file.read()

print(text)

lines = text.splitlines()

players = json.load(open(players_file, "r"))
old_players = players.copy()

bracket_full = []
first_player = ""
overwrite_players = True

for i, line in enumerate(lines):
    if not line:
        continue
    if line in players:
        if first_player == "":
            first_player = line
        else:
            bracket_full.append([first_player, line])
            first_player = ""
    else:
        if not line[0] == "[" and not line.startswith("WOMEN") and not line.startswith("MEN") \
            and not line.startswith("Arthur") and not line.startswith("Match") \
            and not line.startswith("Upcoming") and not line.startswith("Court") \
            and not line.startswith("Louis Armstrong") and not line.startswith("Grandstand") \
            and not (line[0].isupper() and line[1].isupper() and line[2].isupper()):
            print(line + " not found")
            if first_player == "":
                first_player = line
            else:
                bracket_full.append([first_player, line])
                first_player = ""
            # add that player to the players list
            players[line] = ({"seed": 500, "cost": 5000})

with open(bracket_file + ".json", "w") as f:
    json.dump(bracket_full, f, indent=4)

if len(players) > len(old_players) and overwrite_players:
    with open(players_file, "w") as f:
        json.dump(players, f, indent=4)
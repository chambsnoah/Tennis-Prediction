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
overwrite_players = False

for i, line in enumerate(lines):
    if not line:
        continue
    # the name is the line until there is a number, a "Q", or a "WC"
    name = ""
    line = line.split()
    for word in line:
        if word.isdigit() or word == "Q" or word == "WC" or word == "LL":
            break
        name += word + " "
    name = name.strip()

    if name in players:
        if first_player == "":
            first_player = name
        else:
            bracket_full.append([first_player, name])
            first_player = ""
    else:
        print(name + " not found")
        if first_player == "":
            first_player = name
        else:
            bracket_full.append([first_player, name])
            first_player = ""
        # add that player to the players list
        players[name] = ({"seed": 500, "cost": 5000})

with open(bracket_file + ".json", "w") as f:
    json.dump(bracket_full, f, indent=4)

if len(players) > len(old_players) and overwrite_players:
    with open(players_file, "w") as f:
        json.dump(players, f, indent=4)
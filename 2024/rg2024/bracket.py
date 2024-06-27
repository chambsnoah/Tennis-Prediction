import json

config = "m"

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

lines = text.splitlines()

players = json.load(open(players_file, "r"))
old_players = players.copy()

bracket_full = []
first_player = ""
overwrite_players = False

for i, line in enumerate(lines):
    if not line:
        continue
    # the name is the line until there is a three capital letters or a -
    name = ""
    line = line.split()
    last_name_parts = []
    first_name_parts = []
    for word in line:
        if (word.isupper() and len(word) == 3 \
            and word != "ZHU" and word != "RUS" \
            and word != "VAN" and word != "LYS" \
            and word != "BAI" and word != "DAY") \
            or "---" in word:
            break
        if word.isupper() and not "." in word:
            last_name_parts.append(word)
        else:
            first_name_parts.append(word)
    first_name = first_name_parts[0][0]
    last_name_parts_real = []
    if len(first_name_parts) > 1:
        for word in first_name_parts[1:]:
            last_name_parts_real.append(word.lower().capitalize())
    for word in last_name_parts:
        last_name_parts_real.append(word.lower().capitalize())
    last_name = " ".join(last_name_parts_real)
    formatted_name = f"{first_name[0]}. {last_name}"
    print(formatted_name)
    name = formatted_name.strip()

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
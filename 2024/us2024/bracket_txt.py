import json

config = "f"

if config == "m":
    bracket_txt = "bracket_male.txt"
    players_json = "players_male.json"
    bracket_json = "bracket_male.json"
elif config == "f":
    bracket_txt = "bracket_female.txt"
    players_json = "players_female.json"
    bracket_json = "bracket_female.json"

# read the file
file = open(bracket_txt, "r")
text = file.read()

# split the text line by line
lines = text.splitlines()

players = json.load(open(players_json, "r"))

bracket_full = []
first_player = ""

for i, line in enumerate(lines):
    print(i,line)
    if line.upper() in players:
        print(line)
        if first_player == "":
            first_player = line
        else:
            bracket_full.append([first_player.upper(), line.upper()])
            first_player = ""
    else:
        if not line[0].isdigit() and line != "first round":
            print(line + " not found")

with open(bracket_json, "w") as f:
    json.dump(bracket_full, f, indent=4)
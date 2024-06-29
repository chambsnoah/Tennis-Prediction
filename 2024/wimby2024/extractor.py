# open the players_male.txt file
config = "m"

# open the txt file (gotten from just plain selecting the text from the power rankings page)
file_name = ""
if config == "m":
    file_name = "players_male.txt"
elif config == "f":
    file_name = "players_female.txt"

# read the file
file = open(file_name, "r")
text = file.read()

print(text)

# split the text line by line
lines = text.splitlines()

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

players = {}
seed = 1

for i, line in enumerate(lines):
    name = ""
    rank = 0
    cost = 0
    # if the line is empty, skip it
    if not line:
        continue
    # only get the part before the (
    line = line.split("(")[0]
    # split the line by spaces
    line = line.split(" ")
    # get the seed
    seed = int(line[0])
    # get the cost
    cost = seed_to_cost(seed)
    # the name is the rest of the line written LASTNAME, Firstname.
    name = " ".join(line[1:])
    # We want it to be F. Lastname (or F. LASTNAME is fine also)
    name = name.split(",")[1][1] + ". " + name.split(",")[0]
    # add the player to the list
    players[name] = ({"seed": seed, "cost": cost})
    # increment the seed
    seed += 1

# export the list of players to a json file
import json

if config == "m":
    with open("players_male.json", "w") as f:
        json.dump(players, f, indent=4)
elif config == "f":
    with open("players_female.json", "w") as f:
        json.dump(players, f, indent=4)


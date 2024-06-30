# open the players_male.txt file
config = "f"

# open the txt file (gotten from just plain selecting the text from the power rankings page)
file_name = ""
if config == "m":
    file_name = "players_male_atp.txt"
elif config == "f":
    file_name = "players_female_wta.txt"

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
first_name = ""
last_name = ""

for i, line in enumerate(lines):
    name = ""
    rank = 0
    cost = 0
    # if the line is empty, skip it
    if not line:
        continue
    if line.isdigit() or line == "-":
        # next line will be first name
        first_name = lines[i+1]
        last_name = lines[i+2]
        rank = seed
        cost = seed_to_cost(rank)
    
        name = (first_name[0] + ". " + last_name).upper()
        # add the player to the list
        players[name] = ({"seed": seed, "cost": cost, "p_factor": 0, "n_factor": 0})

        seed += 1

# export the list of players to a json file
import json

if config == "m":
    with open("players_male.json", "w") as f:
        json.dump(players, f, indent=4)
elif config == "f":
    with open("players_female.json", "w") as f:
        json.dump(players, f, indent=4)


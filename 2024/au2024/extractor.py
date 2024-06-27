import json

config = "f"

# open the txt file (gotten from just plain selecting the text from the power rankings page)
file_name = ""
if config == "m":
    file_name = "players_male"
elif config == "f":
    file_name = "players_female"

players = []

with open(file_name + ".txt", "r") as file:
    for line in file:
        players.append(line.strip().split("\t"))

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

seed = 1
players_dict = {}

for player in players:
    print(player)
    name = player[2].split() # for men player[1].split() if player[0].isdigit() else player[0].split()
    first_initial = name[0][0]
    last_name = name[-1]
    cost = seed_to_cost(seed)
    players_dict[f"{first_initial}. {last_name}"] = {"seed": seed, "cost": cost}
    seed += 1

# export the list of players to a json file
with open(file_name + ".json", "w") as f:
    json.dump(players_dict, f, indent=4)
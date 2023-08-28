import json

config = "m"

# open the txt file (gotten from just plain selecting the text from the power rankings page)
file_name = ""
if config == "m":
    file_name = "players_male"
elif config == "f":
    file_name = "players_female"

file = open(file_name + ".txt", "r")
 
# read the file
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
power = 0
prevWasDigit = False
past_number_1 = 0
past_number_2 = 0

for i, line in enumerate(lines):
    # if the line is empty, skip it
    if not line:
        continue
    # if line contains a number, skip it
    if any(char.isdigit() for char in line):
        if line[0].isdigit():
            # if it starts with a number, we assume that is the seed or the power
            # the power is before the seed
            if past_number_1 == 0:
                past_number_1 = int(line)
            elif past_number_2 == 0:
                past_number_2 = int(line)
        prevWasDigit = True
        continue

    if prevWasDigit:
        # split the line by spaces
        line = line.split(" ")
        # get the cost
        cost = seed_to_cost(past_number_2)
        # get the power
        power = past_number_1
        # get the seed
        seed = past_number_2
        # We want it to be F. Lastname (or F. LASTNAME is fine also)
        name = line[0][0] + ". " + " ".join(line[1:])
        # add the player to the list
        players[name] = ({"seed": seed, "cost": cost, "power": power})

    past_number_1 = 0
    past_number_2 = 0
    prevWasDigit = False

# export the list of players to a json file
with open(file_name + ".json", "w") as f:
    json.dump(players, f, indent=4)
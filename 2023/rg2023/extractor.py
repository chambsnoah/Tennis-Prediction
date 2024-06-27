from bs4 import BeautifulSoup

html = open("players_male.html", "r")
soup = BeautifulSoup(html, features="html.parser")

# kill all script and style elements
for script in soup(["script", "style"]):
    script.extract()    # rip it out

# get text
text = soup.get_text()

# break into lines and remove leading and trailing space on each
lines = (line.strip() for line in text.splitlines())
# break multi-headlines into a line each
chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
# drop blank lines
text = '\n'.join(chunk for chunk in chunks if chunk)

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
    # if the line start with a number, then it's a rank
    if line[0].isdigit():
        # the line two lines above is the name
        name = lines[i - 2]
        cost = seed_to_cost(seed)
        # add the player to the list
        name = name.split(" ")[0][0] + "." + " ".join(name.split(" ")[1:])
        players[name] = ({"seed": seed, "cost": cost})
        # increment the seed
        seed += 1

# export the list of players to a json file
import json

with open("players_male.json", "w") as f:
    json.dump(players, f, indent=4)
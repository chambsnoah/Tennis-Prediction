from bs4 import BeautifulSoup

config = "m"

# open the txt file (gotten from just plain selecting the text from the power rankings page)
file_name = ""
if config == "m":
    file_name = "players_male.html"
    players_json = "players_male.json"
elif config == "f":
    file_name = "players_female.html"
    players_json = "players_female.json"

html = open(file_name, "r")
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

players = {}
seed = 1

for i, line in enumerate(lines):
    name = ""
    rank = 0
    cost = 0
    # if the line is empty, skip it
    if not line:
        continue
    # if the line is a number, then it's a rank
    if line.isdigit():
        # the next line is the name
        name = lines[i + 1]
        if name == "Juncheng":
            name = "Juncheng Shang"
            cost = lines[i + 3]
        else:
            # the next line is the cost
            cost = lines[i + 2]
        # the cost is a string of the form "$XX,XXX", so we need to remove the "$" and ","
        cost = int(cost.replace("$", "").replace(",", ""))
        # add the player to the list
        name = (name.split(" ")[0][0] + ". " + " ".join(name.split(" ")[1:])).upper()
        players[name] = ({"seed": seed, "cost": cost, "p_factor": 0, "n_factor": 0})
        # increment the seed
        seed += 1

# export the list of players to a json file
import json

with open(players_json, "w") as f:
    json.dump(players, f, indent=4)
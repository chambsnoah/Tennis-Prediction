import json

from bs4 import BeautifulSoup

config = "m"

if config == "m":
    bracket_html = "bracket_male.html"
    players_json = "players_male.json"
    bracket_json = "bracket_male.json"
elif config == "f":
    bracket_html = "bracket_female.html"
    players_json = "players_female.json"
    bracket_json = "bracket_female.json"

html = open(bracket_html, "r")
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

lines = text.splitlines()

players = json.load(open(players_json, "r"))

bracket_full = []
first_player = ""

for i, line in enumerate(lines):
    if line.upper() in players:
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
import json

bracket = open("bracket_female.txt", "r").read().splitlines()

bracket_full = []

for i, line in enumerate(bracket):
    if i % 2 == 0:
        # remove the last word if it's a number or 'Q', also remove the . at the end of the first word, remove padding
        words_1 = line.strip().split(" ")
        if words_1[-1].isdigit() or words_1[-1] == "Q" or words_1[-1] == "WC" or words_1[-1] == "LL":
            words_1 = words_1[:-1]
        words_1[0] = words_1[0][:-1]
        name1 = " ".join(words_1)

        words_2 = bracket[i + 1].strip().split(" ")
        if words_2[-1].isdigit() or words_2[-1] == "Q" or words_2[-1] == "WC" or words_2[-1] == "LL":
            words_2 = words_2[:-1]
        words_2[0] = words_2[0][:-1]
        name2 = " ".join(words_2)

        bracket_full.append([name1, name2])

with open("bracket_female.json", "w") as f:
    json.dump(bracket_full, f, indent=4)
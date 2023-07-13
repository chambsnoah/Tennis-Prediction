import json
import random
players = json.load(open("players_female.json", "r"))

bracket = json.load(open("bracket_female.json", "r"))

savefile = True
watchplayer = ""

# TODO: make sure the player names are the same in the bracket and in the players file

player_points = {}
for player in players:
    player_points[player] = 0

while True:
    print(bracket)
    next_bracket = []
    for i in range(len(bracket)):
        if i % 2 == 0:
            stats1, stats2 = None, None
            winner1, winner2, loser1, loser2 = None, None, None, None
            player1 = bracket[i][0]
            player2 = bracket[i][1]
            if player1 == watchplayer or player2 == watchplayer:
                print()
                print(player1 + ", " + player2)
                print()
            if player1 in players:
                stats1 = players[player1]
            if player2 in players:
                stats2 = players[player2]
            if stats1 and stats2:
                if player1 == watchplayer:
                    winner1 = player1
                    loser1 = player2
                elif player2 == watchplayer:
                    winner1 = player2
                    loser1 = player1
                else:
                    winner1 = player1 if stats1["seed"] < stats2["seed"] else player2
                    loser1 = player2 if stats1["seed"] < stats2["seed"] else player1
            elif stats1:
                winner1 = player1
                loser1 = player2
            elif stats2:
                winner1 = player2
                loser1 = player1
            player1 = bracket[i + 1][0]
            player2 = bracket[i + 1][1]
            if player1 == watchplayer or player2 == watchplayer:
                print()
                print(player1 + ", " + player2)
                print()
            stats1, stats2 = None, None
            if player1 in players:
                stats1 = players[player1]
            if player2 in players:
                stats2 = players[player2]
            if stats1 and stats2:
                if player1 == watchplayer:
                    winner2 = player1
                    loser2 = player2
                elif player2 == watchplayer:
                    winner2 = player2
                    loser2 = player1
                else:
                    winner2 = player1 if stats1["seed"] < stats2["seed"] else player2
                    loser2 = player2 if stats1["seed"] < stats2["seed"] else player1
            elif stats1:
                winner2 = player1
                loser2 = player2
            elif stats2:
                winner2 = player2
                loser2 = player1
            next_bracket.append([winner1, winner2])
            if winner1 in player_points:
                player_points[winner1] += 55
            if winner2 in player_points:
                player_points[winner2] += 55
            if loser1 in player_points:
                player_points[loser1] += 45
            if loser2 in player_points:
                player_points[loser2] += 45
    bracket = next_bracket
    if len(bracket) == 1:
        print(bracket)
        player1 = bracket[0][0]
        player2 = bracket[0][1]
        stats1, stats2 = None, None
        if player1 in players:
            stats1 = players[player1]
        if player2 in players:
            stats2 = players[player2]
        if player1 == watchplayer:
            winner = player1
        elif player2 == watchplayer:
            winner = player2
        else:
            winner = player1 if stats1["seed"] < stats2["seed"] else player2
            loser = player2 if stats1["seed"] < stats2["seed"] else player1
        player_points[winner] += 55
        player_points[loser] += 45
        bracket = [winner]
        break

print(bracket)
print(player_points)

if savefile:
    with open("player_points_female.json", "w") as f:
        json.dump(player_points, f, indent=4)
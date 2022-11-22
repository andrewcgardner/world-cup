import random

class Draw():
    def __init__(self, pool, competition):
        self.pool = pool
        self.competition = competition
    
    def draw_teams(self):
        players = {}
        for plyr in self.pool.get_players():
            players[plyr.get_name()] = {"teams": [], "groups": []}

        for pot_number in range(1,5):
            current_pot = self.competition.get_teams_by_pot(pot_number)

            for plyr, attrs in players.items():
                for _ in range(len(current_pot)):
                    selected_team = random.choice(current_pot)
                    selected_team_obj = self.competition.get_team_by_name(selected_team)
                    selected_team_group = selected_team_obj.get_team_group()
                    if selected_team_group not in attrs["groups"]:
                        break
                    
                current_pot.remove(selected_team)
                players[plyr]["teams"].append(selected_team)
                players[plyr]["groups"].append(selected_team_group)
        
        return players

        # if self.verify_draw(players):
        #     return players
        # else:
        #     raise Exception("Invalid Draft: Player has too many countries from one group.")

    def verify_draw(self, draft):
        valid = True
        for p in draft.keys():
            groups = draft[p]['groups']
            if len(groups) == len(set(groups)):
                continue
            else:
                valid = False
                break

        return valid 

# handle_last_picks()
    # for pot one, just select teams, record the groups to which the belong
    # for pot two, 

if __name__ == '__main__':

    # import pandas as pd
    # from competition import Competition
    # from team import Team
    
    # c = Competition()
    # teams_df = pd.read_csv('../teams.csv')
    # for _, row in teams_df.iterrows():
    #     t = Team(row['country'], row['group'], row['pot'])
    #     c.add_team(t)

    # player_list = ['bot0', 'bot1', 'bot2', 'bot3', 'bot4', 'bot5', 'bot6', 'bot7']
    # players = {}
    # for plyr in player_list:
    #     players[plyr] = {"teams": [], "groups": []}

    # def get_valid_picks(competition, players, pot_number):
    #     current_pot = competition.get_teams_by_pot(pot_number)
    #     print(f"List of teams in current_pot (pot {pot_number}: {current_pot}")
    #     valid_picks = {}
    #     for plyr, attr in players.items():
    #         group_teams = []
    #         groups_selected = attr['groups']
    #         print(f"Groups already selected for {plyr}: {groups_selected}")
            
    #         for group in groups_selected:
    #             group_teams.append(c.get_teams_by_group(group))
    #         print(f"Teams included in selected groups: {group_teams}")

    #         valid_picks[plyr] = [country for country in current_pot if country not in group_teams]
    #         print(f"Teams available for selection after group check: {valid_picks[plyr]}")
        
    #     return valid_picks


    # def check_other_teams(valid_picks, selected_team, current_player):
    #     valid = True    
    #     for p, picks in valid_picks.items():
    #         if p == current_player:
    #             next
    #         else:
    #             potential_picks = [pick for pick in picks if pick != selected_team]
    #             if len(potential_picks) == 0:
    #                 print(f"Oh no!  Choosing {selected_team} for {plyr} would leave {p} with no valid picks!")
    #                 valid = False
            
    #     return valid

    # def select_team(competition, list_of_teams, available_groups):
    #     for _ in range(len(list_of_teams)):
    #         selected_team = random.choice(list_of_teams)
    #         selected_team_obj = competition.get_team_by_name(selected_team)
    #         selected_team_group = selected_team_obj.get_team_group()
            
    #         if selected_team_group not in available_groups:
    #             break
        
    #     return [selected_team, selected_team_group]

    # def draw_teams(competition, players):
    #     for pot_number in range(1,5):
    #         valid_picks = get_valid_picks(competition, players, pot_number)
    #         current_pot = competition.get_teams_by_pot(pot_number) # this is redundant, could be passed to line above
    #         print(f"Drawing teams from Pot {pot_number}.")
    #         for plyr, attrs in players.items():
    #             valid_pick = False
    #             while valid_pick == False:
    #                 team_info = select_team(competition, current_pot, attrs["groups"])  
    #                 print(f"Attempting to select {team_info[0]} for {plyr}")  
                    
    #                 if check_other_teams(valid_picks, team_info[0], plyr):
    #                     print(f"Selecting {team_info[0]} for {plyr} won't impact anyone else.")
    #                     valid_pick = True
    #                 else:
    #                     continue

    #             current_pot.remove(team_info[0])
    #             print(f"Teams remaining after selection: {current_pot}")
    #             players[plyr]["teams"].append(team_info[0])
    #             players[plyr]["groups"].append(team_info[1])
    #             for p, a in players.items():
    #                 print(f"{p}: {a}")
    #             for p, picks in valid_picks.items():
    #                 try:
    #                     picks.remove(team_info[0])
    #                 except:
    #                     next
    #             valid_picks.pop(plyr, None)
    #             for v, p in valid_picks.items():
    #                 print(f"{v}: {p}")
        
    #     return players


    # draft = draw_teams(c, players)
    # for d, s in draft.items():
    #     if len(s["groups"]) != len(set(s["groups"])): 
    #         print(f"{d}: {s} -- Invalid Selection!")
    #     else:
    #         print(f"{d}: {s}")

    
        



# for each pot
    # for each player
        # try to select a team
            # check that the team's group is not in the list of groups already selected
            # check to see that selecting this team will not leave another team with no other options
        # if successful
            # select the team
                # add team name to the list
                # add group name to the list
                # remove team from current pot teams
                # remove team from valid picks for all players
                # remove player entirely? avoid checking CURRENT player
        # if not:
            #
            # 
# maybe an alternate approach is to sort by the team with the fewest available options first, and let them get their choice out of the way?
    # or would this leave us in the same situation where the last 2-3 teams in each pot get screwed?

            # return(sorted(tup, key = lambda x: x[1]))

            # tup.sort(key = lambda x: x[1])
            # return tup

    import random
    import copy
    # all_teams = [
    #     ['a', [1,2,3,4]],
    #     ['b', [1,2,3,4]],
    #     ['c', [1,2,3,4]],
    #     ['d', [1,2,3,4]],
    #     ['e', [1,2,3,4]],
    #     ['f', [1,2,3,4]],
    #     ['g', [1,2,3,4]],
    #     ['h', [1,2,3,4]]
    # ]
    all_teams = {
        'a': [1,2,3,4],
        'b': [1,2,3,4],
        'c': [1,2,3,4],
        'd': [1,2,3,4],
        'e': [1,2,3,4],
        'f': [1,2,3,4],
        'g': [1,2,3,4],
        'h': [1,2,3,4]
    }
    # print(all_teams[0][1][2])

    # players = [
    #     ['bot0', [], []],
    #     ['bot1', [], []],
    #     ['bot2', [], []],
    #     ['bot3', [], []],
    #     ['bot4', [], []],
    #     ['bot5', [], []],
    #     ['bot6', [], []],
    #     ['bot7', [], []]
    # ]
    # players = {
    #     'bot0': {"group": [], "pot":[]},
    #     'bot1': {"group": [], "pot":[]},
    #     'bot2': {"group": [], "pot":[]},
    #     'bot3': {"group": [], "pot":[]},
    #     'bot4': {"group": [], "pot":[]},
    #     'bot5': {"group": [], "pot":[]},
    #     'bot6': {"group": [], "pot":[]},
    #     'bot7': {"group": [], "pot":[]},
    # }
    # players = {
    #     0: {"group": [], "pot":[]},
    #     1: {"group": [], "pot":[]},
    #     2: {"group": [], "pot":[]},
    #     3: {"group": [], "pot":[]},
    #     4: {"group": [], "pot":[]},
    #     5: {"group": [], "pot":[]},
    #     6: {"group": [], "pot":[]},
    #     7: {"group": [], "pot":[]},
    # }
    players = {
        '0': {"group": [], "pot":[]},
        '1': {"group": [], "pot":[]},
        '2': {"group": [], "pot":[]},
        '3': {"group": [], "pot":[]},
        '4': {"group": [], "pot":[]},
        '5': {"group": [], "pot":[]},
        '6': {"group": [], "pot":[]},
        '7': {"group": [], "pot":[]},
    }

    groups = ['a','b','c','d','e','f','g','h']
    # for x in range(1,5):
    #     all_teams_copy = copy.deepcopy(all_teams)
    #     players_copy = copy.deepcopy(players)
    #     groups_copy = copy.deepcopy(groups)
    #     for i in range(len(players)):

    #         # current_player = players_copy[str(i)]
    #         current_player = str(i)
    #         # print(players[current_player])
    #         # group = random.choice(all_teams_copy)
    #         # print(f"{group[0]}{group[1][0]}")

    #         # attempt to make selection, don't pick it if it's a duplicate
    #         valid_group = False
    #         break_out = False
    #         while not valid_group:
    #             group = random.choice(groups_copy)
    #             if group in players_copy[current_player]["group"]:
    #                 print("Group {} already selected for {}".format(group, current_player))
    #                 continue
    #             else:
    #                 for p, attrs in players_copy.items():
    #                     if p == current_player:
    #                         next
    #                     elif len([g for g in groups_copy if g != group]) == 0:
    #                         print("Selecting {} for {} will leave {} with no available choices.".format(group, current_player, p))
    #                         break_out = True
    #                         break
    #                 if break_out:
    #                     break
    #                 else:
    #                     valid_group = True

    #         # group_key = all_teams_copy[group]

            
    #         # remove items from copy objects
    #         remaining_groups = groups_copy.remove(group)
    #         players_copy.pop(current_player)

    #         # add to main object
    #         players[current_player]["group"].append(group)
    #         players[current_player]["pot"].append(x)

    # for p, a in players.items():
    #     if len(a['group']) != len(set(a['group'])):
    #         print(f"{p}: {a['group']} -- INVALID!")
    #     else:
    #         print(f"{p}: {a['group']}")

    pot1 = ['a','b','c','d','e','f','g','h']
    pot2 = copy.deepcopy(pot1)
    pot3 = copy.deepcopy(pot1)
    pot4 = copy.deepcopy(pot1)

    pot_length = len(pot1)

    random.shuffle(pot1)
    print(f"Pot 1: {pot1}")
    valid_order = False
    counter = 0
    
    while not valid_order:
        num_errors = 0
        counter += 1
        print(f"\nShuffle Iteration: {counter}")
        random.shuffle(pot2)
        for i in range(pot_length):
            if pot1[i] == pot2[i]:
                num_errors +=1
        
        if num_errors > 0:
            print(f"Pot 2: {pot2} -- INVALID!")
            continue
        else:
            valid_order = True
            print(f"Pot 1: {pot1}")
            print(f"Pot 2: {pot2}")

    valid_order = False
    counter = 0

    while not valid_order:
        num_errors = 0
        counter += 1
        print(f"\nShuffle Iteration: {counter}")
        random.shuffle(pot3)
        for i in range(pot_length):
            if pot3[i] == pot1[i] or pot3[i] == pot2[i]:
                num_errors +=1
        
        if num_errors > 0:
            print(f"Pot 3: {pot3} -- INVALID!")
            continue
        else:
            valid_order = True
            print(f"Pot 1: {pot1}")
            print(f"Pot 2: {pot2}")
            print(f"Pot 3: {pot3}")


    valid_order = False
    counter = 0

    while not valid_order:
        num_errors = 0
        counter += 1
        print(f"\nShuffle Iteration: {counter}")
        random.shuffle(pot4)
        for i in range(pot_length):
            if pot4[i] == pot1[i] or pot4[i] == pot2[i] or pot4[i] == pot3[i]:
                num_errors +=1
        
        if num_errors > 0:
            print(f"Pot 3: {pot3} -- INVALID!")
            continue
        else:
            valid_order = True
            print(f"Pot 1: {pot1}")
            print(f"Pot 2: {pot2}")
            print(f"Pot 3: {pot3}")
            print(f"Pot 4: {pot4}")

            
            
        
    # print(f"Pot 2: {pot2}")
        # if not the_pots_match:
        #     print(f"Pot 2: {pot2}")
        #     break


# while true
    # check each item in the list
        # if they are all different, 






from draw import Draw
from pool import Pool
from team import Team
from player import Player
from competition import Competition
from presentation import Presentation
import pandas as pd

def team_menu(t):
    menu = {
        "1": "Display Teams.",
        "2": "Display Pot.",
        "3": "Swap Pots.",
        "4": "<-- Back to Main Menu."
    }
    while True:
        options=menu.keys()
        print('\n')
        for entry in options: 
            print(entry, menu[entry])

        selection = input("\nPlease Select: ") 
        if selection == '1': 
            t.display_teams()
        elif selection == '2':
            pot_choice = int(input("Please Select Pot Number (1-4): "))
            print(t.get_teams_by_pot(pot_choice))
        elif selection == '3':
            team1 = input("Please select the first team to swap: ")
            team2 = input("Please select the second team to swap: ")
            t.swap_pots(team1, team2)
            # print("Swapped Pots for {} and {}".format(team1, team2))
        elif selection == '4': 
            break
        else: 
            print("Unknown Option Selected!")

def player_menu(p):
    menu = {
        "1": "Display Players.",
        "2": "Add Player(s).",
        "3": "<-- Back to Main Menu."
    }
    while True:
        options=menu.keys()
        print('\n')
        for entry in options: 
            print(entry, menu[entry])

        selection = input("\nPlease Select: ") 
        if selection == '1': 
            p.list_players()
        elif selection == '2':
            while True:
                try:
                    num_players = int(input("How many players would you like to add?: ")) # needs to only accept integer
                    break
                except ValueError:
                    print("Please enter integer value.")

            for i in range(0, num_players):
                pname = input("Please enter a name for Player {}: ".format(i + 1))
                plyr = Player(pname)
                p.add_player(plyr)
            print("Players added successfully.")
        elif selection == '3':
            break
        else: 
            print("Unknown Option Selected!")


def run():
    menu = {}
    menu['1']="Teams Management." 
    menu['2']="Player Management."
    menu['3']="Conduct Draft."
    menu['4']="Exit."
    p = Pool()
    c = Competition()
    print("Initializing Competition...")
    df = pd.read_csv('../teams.csv')
    for _, row in df.iterrows():
        t = Team(row['country'], row['group'], row['pot'])
        c.add_team(t)
    print("Teams loaded successfully.")
    
    while True: 
        options=menu.keys()
        print('\n')
        for entry in options: 
            print(entry, menu[entry])

        selection = input("\nPlease Select: ") 
        if selection == '1': 
            team_menu(c)
        
        elif selection == '2':
            player_menu(p)
        
        elif selection == '3':
            team_count = len(c.get_teams_by_pot(1))
            plyr_count = len(p.get_players())
            # num_pots = 4
            # groups = ['a','b','c','d','e','f','g','h']
            num_pots = len(c.get_pots())
            groups = c.get_groups()
            d = Draw(num_pots, groups)

            if team_count > plyr_count:
                while True:
                    plyr_count_response = input("There are fewer players than teams. Would you like to add more players? (y/n): ")
                    if plyr_count_response == "y":
                        print("Please navigate back to Player Management to add more players.")
                        break
                    elif plyr_count_response == "n":
                        players_needed = team_count - plyr_count
                        for i in range(0, players_needed):
                            bot = Player("bot{}".format(i))
                            p.add_player(bot)

                        draft = d.draw_teams()
                        draft_obj = d.load_teams(draft)
                        draft_order = p.get_draft_order()
                        mapped_draft = p.map_players_to_draw(draft_obj, draft_order)
                        mapped_draft = c.map_teams_to_draw(mapped_draft)
                        pr = Presentation(mapped_draft)
                        pr.present_draft(num_pots)
                        break
                    else:
                        print("Unknown Option Selected!")
            else:
                draft = d.draw_teams()
                draft_obj = d.load_teams(draft)
                draft_order = p.get_draft_order()
                mapped_draft = p.map_players_to_draw(draft_obj, draft_order)
                mapped_draft = c.map_teams_to_draw(mapped_draft)
                pr = Presentation(mapped_draft)
                pr.present_draft(num_pots)
                
        
        elif selection == '4': 
            break
        else: 
            print("Unknown Option Selected!")

if __name__ == '__main__':
    run()


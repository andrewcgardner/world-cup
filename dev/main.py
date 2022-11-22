from pool import Pool
from player import Player
from teams import Teams

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
            print(t.get_teams())
        elif selection == '2':
            pot_choice = int(input("Please Select Pot Number (1-4): "))
            print(t.get_pot(pot_choice))
        elif selection == '3':
            team1 = input("Please select the first team to swap: ")
            team2 = input("Please select the second team to swap: ")
            t.swap_pots(team1, team2)
            print("Swapped Pots for {} and {}".format(team1, team2))
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
            num_players = int(input("How many players would you like to add?: "))
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
    t = Teams()
    
    while True: 
        options=menu.keys()
        print('\n')
        for entry in options: 
            print(entry, menu[entry])

        selection = input("\nPlease Select: ") 
        if selection == '1': 
            team_menu(t)
        
        elif selection == '2':
            player_menu(p)
        
        elif selection == '3':
            team_count = t.get_pot(1).shape[0]
            plyr_count = len(p.get_players())

            if team_count > plyr_count:
                plyr_count_response = input("There are fewer players than teams. Would you like to add more players? (y/n): ")
                if plyr_count_response == "y":
                    print("Please navigate back to Player Management to add more players.")
                elif plyr_count_response == "n":
                    players_needed = team_count - plyr_count
                    # while players_needed > 0:
                    for i in range(0, players_needed):
                        bot = Player("bot{}".format(i))
                        p.add_player(bot)
                        # players_needed -= 1
                    t.draft_teams()
                else:
                    print("Unknown Option Selected!")  
            else:      
                t.draft_teams()
        
        elif selection == '4': 
            break
        else: 
            print("Unknown Option Selected!")

if __name__ == '__main__':
    run()



# def run():
#     menu = {}
#     menu['1']="Display Teams." 
#     menu['2']="Display Pot."
#     menu['3']="Swap Pots."
#     menu['4']="Add Players."
#     menu['5']="Conduct Draft."
#     menu['6']="Exit."
#     p = Pool()
#     t = Teams()
    
#     while True: 
#         options=menu.keys()
#         print('\n')
#         for entry in options: 
#             print(entry, menu[entry])

#         selection = input("\nPlease Select: ") 
#         if selection == '1': 
#             print(t.get_teams())
#         elif selection == '2':
#             pot_choice = int(input("Please Select Pot Number (1-4): "))
#             print(t.get_pot(pot_choice))
#         elif selection == '3':
#             team1 = input("Please select the first team to swap: ")
#             team2 = input("Please select the second team to swap: ")
#             t.swap_pots(team1, team2)
#             print("Swapped Pots for {} and {}".format(team1, team2))
#         elif selection == '4':
#             num_players = int(input("How many players would you like to add?: "))
#             for i in range(0, num_players):
#                 pname = input("Please enter a name for Player {}: ".format(i + 1))
#                 plyr = Player(pname)
#                 p.add_player(plyr)
            
#             print(p.get_players())
#         elif selection == '5':
#             team_count = t.get_pot(1).shape[0]
#             plyr_count = len(p.get_players())

#             while team_count > plyr_count:
#                 plyr_count_response = input("There are fewer players than teams. Would you like to add more players? (y/n): ")
#                 if plyr_count_response == "y":
#                     break
#                 elif plyr_count_response == "n":
#                     players_needed = team_count - plyr_count
#                     while players_needed > 0:
#                     # for i in range(0, players_needed):
#                         bot = Player("bot{}".format(i))
#                         p.add_player(bot)
#                         players_needed -= 1
#                 else:
#                     print("Unknown Option Selected!")        
#             t.draft_teams()
#         elif selection == '6': 
#             break
#         else: 
#             print("Unknown Option Selected!")
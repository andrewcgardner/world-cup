import time
import random

class Presentation():
    def __init__(self, draft_obj):
        self.draft_obj = draft_obj
        self.draft_order = list(self.draft_obj.keys())

    def list_pot_teams(self, pot_number):
        teams = []
        for _, v in self.draft_obj.items():
            teams.append(v[pot_number])
        return teams
        
    def display_welcome(self):
        print("\n"*3)
        print("Welcome to the official drawing for the @BraintreeBoyz World Cup 2022 Pool.\n")
        time.sleep(3)
        print("Without further ado...\n")
        time.sleep(3)
    
    def display_draft_order(self, sleep_value=3):
        print("Here is the order in which players will be assigned teams:\n")
        for i in reversed(range(len(self.draft_order))):
            time.sleep(sleep_value)
            print(f"{i+1} - {self.draft_order[i]}")
        print("\n")
        time.sleep(sleep_value)

    def display_draft_pots(self, num_pots=0):
        first_displayed = True
        for pot in reversed(range(num_pots)):
            time.sleep(2)
            pot_teams = self.list_pot_teams(pot)
            random.shuffle(pot_teams)
            print(f"\nNow drawing teams from Pot {pot+1}:\n")
            print(f"Teams in this pot include:\n {', '.join([str(x) for x in pot_teams])}\n")
            time.sleep(3)
            for player in self.draft_order:
                print(f"{player:>5}: {self.draft_obj[player][pot]:>12}")
                time.sleep(3)
            if not first_displayed:
                time.sleep(2)
                self.display_team_summary(num_pots, pot)
            else:
                first_displayed = False

    def display_team_summary(self, total_rounds, current_pot):
        time.sleep(2)
        rounds_to_display = [i+1 for i in reversed(range(0, total_rounds)) if i >= current_pot]
        rounds_completed = [f"Pot {i}" for i in rounds_to_display]
        print(f"\nHere is a review of the squads after {len(rounds_completed)} rounds:\n")
        time.sleep(3)

        format_row = "{:>15}" * (len(rounds_completed) + 1)
        print(format_row.format("", *rounds_completed))
        for k, v in self.draft_obj.items():
            row = [v[i-1] for i in rounds_to_display]
            print(format_row.format(k, *row))
    
    def display_farewell(self):
        time.sleep(3)
        print("\nBest of luck to everyone!\n")
        
    def present_draft(self, num_pots):
        self.display_welcome()
        self.display_draft_order()
        self.display_draft_pots(num_pots=num_pots)
        self.display_farewell()


if __name__ == '__main__':
    
    draft_obj = {
        '0': ['h1', 'c2', 'f3', 'd4'],
        '1': ['a1', 'e2', 'd3', 'b4'],
        '2': ['f1', 'b2', 'c3', 'a4'],
        '3': ['e1', 'g2', 'b3', 'c4'],
        '4': ['c1', 'f2', 'h3', 'g4'],
        '5': ['g1', 'a2', 'e3', 'f4'],
        '6': ['d1', 'h2', 'g3', 'e4'],
        '7': ['b1', 'd2', 'a3', 'h4']
    }
    p = Presentation(draft_obj)
    rounds_completed = 3
    current_round = 2
    total_rounds = 4
    p.display_team_summary(total_rounds, current_round)
    d = {
        'conor': 'Ecuador',
        'liam': 'Canada',
        'ringo': 'Costa Rica',
        'tom': 'Ghana',
        'andy': 'Saudi Arabia',
        'brian': 'Cameroon',
        'mark': 'Australia',
        'matt': 'Wales'
        }

    for k, v in d.items():
        print(f"{k:>5}: {v:>12}")

import random
import copy

class Draw():
    def __init__(self, num_pots, groups):
        self.num_pots = num_pots
        self.groups = groups
        self.pot_length = len(groups)
    
    def draw_teams(self):
        full_list = []
        first_pot = copy.deepcopy(self.groups)
        random.shuffle(first_pot)
        full_list.append(first_pot)

        for i in range(1, self.num_pots):
            current_pot = copy.deepcopy(self.groups)
            valid_order = False
            while not valid_order:
                num_errors = 0
                random.shuffle(current_pot)
                for existing_pot in full_list:
                    for i in range(self.pot_length):
                        if current_pot[i] == existing_pot[i]:
                            num_errors += 1
                
                if num_errors > 0:
                    continue
                else:
                    valid_order = True
                    full_list.append(current_pot)
        
        return full_list

    def load_teams(self, full_list):
        draft = {}
        for i in range(self.pot_length):
            draft[i] = [f"{f[i]}{idx+1}" for idx, f in enumerate(full_list)]

        return draft



if __name__ == '__main__':

    num_pots = 4
    groups = ['a','b','c','d','e','f','g','h']
    d = Draw(num_pots, groups)
    team_draw = d.draw_teams()
    team_draft = d.load_teams(team_draw)
    
    for k, v in team_draft.items():
        print(f"{k}: {v}")





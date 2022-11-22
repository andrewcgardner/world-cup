class Team():
    def __init__(self, name, group, pot):
        self.__id = f"{group}{pot}"
        self.__name = name
        self.__group = group
        self.__pot = pot
        # self.__player_id = None
        self.__group_wins = 0
        self.__group_losses = 0
        self.__group_draws = 0
        self.__goals_for = 0
        self.__goals_against = 0
        self.__group_rank = 0
        self.__round_of_16_w = 0
        self.__quarter_finals_w = 0
        self.__semi_finals_w = 0
        self.__finals_w = 0
    
    def get_team_id(self):
        return self.__id
    
    def get_team_name(self):
        return self.__name
    
    def get_team_group(self):
        return self.__group

    def get_team_pot(self):
        return self.__pot

    def get_team_record(self):
        return [self.__group_wins, self.__group_draws, self.__group_losses]

    def get_team_goal_diff(self):
        # [ GF, GA, (GF - GA) = GD ]
        return [self.__goals_for, self.__goals_against, self.__goals_for - self.__goals_against]

    def set_team_pot(self, new_pot_number):
        self.__pot = new_pot_number
        return self.__pot
    
    def set_team_id(self):
        self.__id = f"{self.__group}{self.__pot}"
    
    # def set_player_id(self, player_id):
    #     self.__player_id = player_id
    #     return self.__player_id

    def calc_group_points(self):
        if self.__group_rank == 1:
            return 3
        elif self.__group_rank == 2:
            return 2
        elif self.__group_rank == 3:
            return 1
        else:
            return 0

    def calculate_points(self):
        team_points = self.calc_group_points()
        team_points += self.__round_of_16_w * 2
        team_points += self.__quarter_finals_w * 2
        team_points += self.__semi_finals_w * 2
        team_points += self.__finals_w * 2

        return team_points
        


if __name__ == '__main__':
    t1 = Team('usa','a',2)
    t2 = Team('canada','b',3)
    t3 = Team('mexico','c',2)

    print(t1.get_team_group())
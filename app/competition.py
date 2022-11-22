class Competition():
    def __init__(self):
        self.__teams = []
        self.__pots = []
        self.__groups = []

    def add_team(self, team_object):
        if self.get_team_by_name(team_object.get_team_name()):
            print("A team by that name already exists.")
        else:
            self.__teams.append(team_object)
            if team_object.get_team_pot() not in self.__pots:
                self.__pots.append(team_object.get_team_pot())
        
            if team_object.get_team_group() not in self.__groups:
                self.__groups.append(team_object.get_team_group())

    def get_pots(self):
        return self.__pots

    def get_groups(self):
        return self.__groups

    def get_team_by_name(self, team_name):
        for team in self.__teams:
            if team.get_team_name() == team_name:
                return team
            else:
                team = None
    
    def get_team_by_id(self, team_id):
        for team in self.__teams:
            if team.get_team_id() == team_id:
                return team
            else:
                return None
    
    def swap_pots(self, team1, team2):
        try:
            t1 = self.get_team_by_name(team1)
            t2 = self.get_team_by_name(team2)

            t1_pot = t1.get_team_pot()
            t2_pot = t2.get_team_pot()

            t1.set_team_pot(t2_pot)
            t2.set_team_pot(t1_pot)

            t1.set_team_id()
            t2.set_team_id()
            print("Swapped pots for {0} ({1} -> {3}) and {2} ({3} -> {1}).".format(team1, t1_pot, team2, t2_pot))
            return True
        except Exception as e:
            print("Failed to swap pots: {}".format(e))
            return False

    def get_teams_list(self):
        return [t.get_team_name() for t in self.__teams]

    def get_teams_by_pot(self, pot_number):
        return [team.get_team_name() for team in self.__teams if team.get_team_pot() == pot_number]
    
    def get_teams_by_group(self, group_letter):
        return [team.get_team_name() for team in self.__teams if team.get_team_group() == group_letter]

    def display_teams(self):
        team_data = [[t.get_team_name(), t.get_team_pot(), t.get_team_group()] for t in self.__teams]
        groups = self.get_groups()
        team_dict = {group:{x[1]: x[0] for x in team_data if x[2] == group} for group in groups}
        
        num_groups = len(groups)
        pots = sorted(self.get_pots())
        num_clusters = 2
        groups_per_cluster = int(num_groups/num_clusters)
        starting_index = 0
        print("\n")

        for _ in range(num_clusters):
            active_groups = [g for g in groups[starting_index:groups_per_cluster]]
            headers = [f"Group {g.upper()}" for g in active_groups]
            format_row = "{:>15}" * (len(headers)+ 1)
            print(format_row.format("", *headers))
            
            for pot in pots:
                row = [team_dict[group][pot] for group in active_groups]
                print(format_row.format(f"Pot {pot}", *row))

            print("\n")
            starting_index += groups_per_cluster
            groups_per_cluster += groups_per_cluster
            

    def map_teams_to_draw(self, draft_obj):
        mapping_dict = {team.get_team_id(): team.get_team_name() for team in self.__teams}
        new_obj = {}
        for k, v in draft_obj.items():
            new_obj[k] = [mapping_dict[id] for id in v]

        return new_obj

        



if __name__=='__main__':
    import pandas as pd
    from team import Team   
    
    print("\nTEST CASE #1 - Load Teams from CSV")
    c = Competition()
    
    df = pd.read_csv('../teams.csv')
    for _, row in df.iterrows():
        t = Team(row['country'], row['group'], row['pot'])
        c.add_team(t)

    print("\nTEST CASE #2: get_teams_list()")
    print(c.get_teams_list())

    print("\nTEST CASE #3: get_team_by_name('Spain')")
    print(c.get_team_by_name('Spain').get_team_name())
    # print("Failing for some unknown reason")
    
    print("\nTEST CASE #4: get_teams_by_pot(1)")
    print(c.get_teams_by_pot(1))

    print("\nTEST CASE #5 - Prevent Duplicate Team Names")
    t1 = Team('Spain','a',1)
    c.add_team(t1)

    print("\nTEST CASE #6 - Swap Pots")
    c.swap_pots("Qatar", "Germany")
    print(c.get_teams_by_pot(1))

    print("\nTEST CASE #7: map_teams_to_draw()")
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
    print(c.map_teams_to_draw(draft_obj))
    
    print("\nTEST CASE #8 display_teams()")
    c.display_teams()
    
    

            
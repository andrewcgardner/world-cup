import pandas as pd

class Teams():
    def __init__(self):
        self.__df = pd.read_csv('teams.csv')
        self.__draft = {}

    def swap_pots(self, team1, team2):
        team1_pot = self.__df[self.__df.country == team1].pot
        team2_pot = self.__df[self.__df.country == team2].pot

        team1_idx = self.__df[self.__df.country == team1].index
        team2_idx = self.__df[self.__df.country == team2].index

        self.__df.loc[team1_idx, 'pot'] = int(team2_pot)
        self.__df.loc[team2_idx, 'pot'] = int(team1_pot)

    def get_pot(self, pot_number):
        return self.__df[self.__df.pot == pot_number]

    def get_teams(self):
        return self.__df
    
    def shuffle_pot_teams(self, pot_df):
        return pot_df.sample(frac=1).reset_index(drop=True)

    def draft_teams(self):
        for p in range(1,5):
            pot = self.get_pot(p)
            pot = self.shuffle_pot_teams(pot)
            
            for i in range(0,pot.shape[0]):
                if i in self.__draft.keys():
                    self.__draft[i][p] = pot.loc[i, 'country']
                else:
                    self.__draft[i] = {p: pot.loc[i, 'country']}

              
        
        print("Draft Complete.\n")
        for k in self.__draft.items():
            print(k)
            

        

if __name__=='__main__':
    t = Teams()
    t.draft_teams()
    

            
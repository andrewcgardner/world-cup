import random

class Pool():
    def __init__(self):
        self.__players = []
        # self.__settings = {}

    def add_player(self, player):
        self.__players.append(player)
    
    def list_players(self):
        for p in self.__players:
            print(p.get_name())
    
    def get_players(self):
        return self.__players
    
    def get_player_by_name(self, name):
        return True

    def get_draft_order(self):
        list_of_players = [p.get_name() for p in self.__players]
        random.shuffle(list_of_players)
        return list_of_players

    def map_players_to_draw(self, draft_obj, draft_order):
        return {draft_order[int(i)]: v for i, v in draft_obj.items()}
import random

class Player():
    def __init__(self, name):
        self.__name = name
        # self.__teams = {}
        self.__id = random.randint(100, 999)
        # self.__draft_order = 0

    def get_name(self):
        return self.__name

    # def get_player_teams(self):
    #     return self.__teams

    def get_player_id(self):
        return self.__id
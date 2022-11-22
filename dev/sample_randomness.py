import random

class DivMatchups(object):
	def __init__(self, league_dict):
		self.league = league_dict
		self.unpicked = [team for teams in [self.league[div] for div in self.league.keys()] for team in teams]
		self.picked = []
		self.matchups = []

	def compile_lists(self, *lists):
		new_list = []
		for i in lists:
			new_list.extend(i)
		return new_list

	def which_division(self, manager):
		for division in self.league:
			if manager in self.league[division]:
				return division

	def get_mgr_from_list(self, manager_list):
		return manager_list[random.randint(0,len(manager_list) - 1)]

	def get_opponents(self, division_name):
		league_list = [self.league[div] for div in self.league.keys() if div != division_name]
		# return [team for teams in league_list for team in teams]
		return [team for teams in [self.league[div] for div in self.league.keys() if div != division_name] for team in teams]

	def filter_opponents(self, division_name):
		opps = self.get_opponents(division_name)
		return [mgr for mgr in opps if mgr in self.unpicked]

	def set_matchup(self, target_div='any'):
		if len(self.unpicked) == 6:
			target_div = self.handle_final_rounds(remaining_managers=6)
		elif len(self.unpicked) == 4:
			target_div = self.handle_final_rounds(remaining_managers=4)

		mgr = self.pick_manager(division=target_div)
		mgr_div = self.which_division(mgr)
		print("{}: {}".format(mgr, mgr_div))

		opponent_pool = self.filter_opponents(mgr_div)
		print("Possible Opponents ({}): {}".format(len(opponent_pool), opponent_pool))
		opp = self.pick_manager(manager_list=opponent_pool)
		print("Matchup: {} vs. {}".format(mgr, opp))

		print("Unpicked ({}): {}".format(len(self.unpicked), self.unpicked))
		print("Picked ({}): {}\n".format(len(self.picked), self.picked))
		self.matchups.append([mgr, opp])

	def make_selection(self, manager):
		self.unpicked.remove(manager)
		self.picked.append(manager)

	def pick_manager(self, manager_list=None, division='any'):
		if manager_list is None:
			manager_list = self.unpicked

		while True:
			mgr = self.get_mgr_from_list(manager_list)
			print("Selected {}".format(mgr))
			if division != 'any':
				print("Need to select a manager from {}".format(division))
				mgr_div = self.which_division(mgr)
				if mgr_div == division:
					print("Manager is from the correct division")
					break
				else:
					print("Manager is not in the desired division, picking again")
			else:
				break

		self.make_selection(mgr)
		return mgr

	def handle_final_rounds(self, remaining_managers=None, manager_list=None):
		if manager_list is None:
			manager_list = self.unpicked

		div_counts = self.get_division_counts(manager_list)
		print(div_counts)
		value_list = list(div_counts.values())
		value_list.sort(reverse=True)

		if remaining_managers == 6:
			if value_list == [3,2,1] or value_list == [3,1,1,1]:
				for div in div_counts.keys():
					if div_counts[div] == 3:
						return div
		elif remaining_managers == 4: 
			if value_list == [2,1,1]:
				for div in div_counts.keys():
					if div_counts[div] == 2:
						return div

		return 'any'

	def get_division_counts(self, manager_list):
		counts = {}	
		for mgr in manager_list:
			mgr_div = self.which_division(mgr)
			if mgr_div not in counts.keys():
				counts[mgr_div] = 1
			else:
				counts[mgr_div] += 1
		return counts

	def run(self):
		while len(self.unpicked) > 0:
			self.set_matchup()

		for matchup in self.matchups:
			print("{} vs. {}".format(matchup[0], matchup[1]))


class ConfMatchups(object):
	def __init__(self, league_dict):
		self.league = league_dict
		self.matchups = []

	def get_mgr_from_list(self, manager_list):
		return manager_list[random.randint(0,len(manager_list) - 1)]

	def make_selection(self, manager_list):
		manager = self.get_mgr_from_list(manager_list)
		manager_list.remove(manager)
		return manager

	def set_matchups(self, conf1, conf2):
		while len(conf1) > 0:
			mgr = self.make_selection(conf1)
			opp = self.make_selection(conf2)

			self.matchups.append([mgr, opp])
		
		for matchup in self.matchups:
			print(matchup)


	def run(self):
		american = self.league['american']
		national = self.league['national']
		print(american)
		print(national)
		print('\n')
		self.set_matchups(american, national)




if __name__ == '__main__':

	while True:
		print("\nPlease enter an integer 0-2:\n\t1. Cross-Conference \n\t2. Cross-Division \n\t0. Exit")
		draw_format = input("Your selection: ")
		try:
			draw_int = int(draw_format)
			if draw_int not in [0,1,2]:
				raise ValueError
		except ValueError:
			print("Please enter a valid value.")
			continue

		if draw_int == 1:

			conf_league = {
				"american": ['ringo','condy','brian','matt','grundle','mikami'],
				"national": ['ice ice','conor','tom','gards','devlin','prez']
			}		

			cm = ConfMatchups(conf_league)
			cm.run()

		elif draw_int == 2:
			div_league = {
				"stantz": ['ringo','condy','brian'],
				"zeddemore": ['matt','grundle','mikami'],
				"spengler": ['ice ice','conor','tom'],
				"venkman": ['gards','devlin','prez']
			}

			dm = DivMatchups(div_league)
			dm.run()

		elif draw_int == 0:
			print("Exiting...")
			exit()
		else:
			continue
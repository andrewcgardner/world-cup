World Cup

Current state:
  - This is a small console app to manage a randomized draw for a tournament like the World Cup, Champions League, or Euros.
  - The draw randomly assigns one team from each pot (typically numbered one-four) to each of the pool's participants.
  - It ingests a .csv containing the team data (name, group, pot) and allows for adjustments to pot numbers (i.e. for World Cup 2022, Qatar is more deserving of Pot 4 status, than Pot 1).
  - Participants' names can be added, otherwise the pool will fill itself out with "bots" (placeholder).
  - The draw ensures that no participant can be assigned more than one team from any group.
  - A "Presentation" class is added to display the results of the draft, selection by selection.
  
Future state:
  - In addition to the draw, my plan is to have this app also manage the pool scoring system.
  - This would include polling APIs to acquire match data and translating those results into "pool points"
  - Also on the to-do list:
    - database implementation
    - UI

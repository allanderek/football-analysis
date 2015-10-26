import blog.posts.league_analysis as league_analysis


def display_table(headers, rows):
    print(headers)
    for row in rows:
        print(row)

def display_bet_analysis(bet_line, match, league, profit_loss=None):
    # So this is the number of goals we would have expected the team to have scored based on shots
    home_shots_goals = match.HS / league.shots_per_goal
    away_shots_goals = match.AS / league.shots_per_goal
    # Similarly for shots on target
    home_sot_goals = match.HST / league.sot_per_goal
    away_sot_goals = match.AST / league.sot_per_goal

    # Who is closer to the shots scorelines, the bet or the real scoreline?
    home_shots_score_diff = abs(match.FTHG - home_shots_goals)
    away_shots_score_diff = abs(match.FTAG - away_shots_goals)
    home_sots_score_diff = abs(match.FTHG - home_sot_goals)
    away_sots_score_diff = abs(match.FTAG - away_sot_goals)

    # home_bet = bet_line.home_score
    # away_bet = bet_line.away_score
    # home_shots_bet_diff = abs(home_bet - home_shots_goals)
    # away_shots_bet_diff = abs(away_bet - away_shots_goals)
    # home_sots_bet_diff = abs(home_bet - home_sot_goals)
    # away_sots_bet_diff = abs(away_bet - away_sot_goals)
    
    headers = ['', match.HomeTeam, match.AwayTeam]
    rows = [['Goals', match.FTHG, match.FTAG],
            # ['Bet Goals', home_bet, away_bet],
            ['Shots', match.HS, match.AS],
            ['SOT', match.HST, match.AST],
            ['Shots Scoreline', home_shots_goals, away_shots_goals],
            ['SOT Scoreline', home_sot_goals, away_sot_goals],
            ['Score-Shots Diff', home_shots_score_diff, away_shots_score_diff],
            # ['Bet-Shots Diff', home_shots_bet_diff, away_shots_bet_diff],
            ['Score-Sots Diff', home_sots_score_diff, away_sots_score_diff],
            # ['Bet-Sots Diff', home_sots_bet_diff, away_sots_bet_diff]
            ['Bet', bet_line.bet_result, bet_line.bet_result],
            ['Profit/Loss', profit_loss, profit_loss]
            ]

    display_table(headers, rows)


class BetLine(object):
    def __init__(self, bet_line):
        """Example Correct Score bet line: Bristol Rovers v Barnet: 1 - 1, 7.0
        Example of a Result bet line: Walsall v Doncaster: Walsall, 1.97
        """
        self.parse_result_line(bet_line)

    def parse_correct_score_line(self, bet_line):
        """Example Correct Score bet line: Bristol Rovers v Barnet: 1 - 1, 7.0
        """
        match_teams, bet_details = bet_line.split(': ')
        self.home, self.away = match_teams.split(' v ')
        bet_score, self.bet_price = bet_details.split(', ')
        home_score, away_score = bet_score.split(' - ')
        self.home_score = int(home_score)
        self.away_score = int(away_score)
    
    def parse_result_line(self, bet_line):
        """Example of a Result bet line: Walsall v Doncaster: Walsall, 1.97
        """
        match_teams, bet_details = bet_line.split(': ')
        self.home, self.away = match_teams.split(' v ')
        result, self.bet_price = bet_details.split(', ')
        if result == "The Draw":
            self.bet_result = 'D'
        elif result == self.home:
            self.bet_result = 'H'
        else:
            assert result == self.away
            self.bet_result = 'A'
    
    def get_relevant_match(self, league, start_date, end_date):
        home = league_analysis.alias_team(self.home)
        away = league_analysis.alias_team(self.away)
    
        matches = league_analysis.get_matches(league, start_date, end_date,
                                              home_team=home, away_team=away)
        match = matches[0]
        self.match = match
        return match

    def get_profit_loss(self, match=None, commission=0.05):
        if match is None:
            match = self.match
        # The amount of money you get back is the odds multiplied by
        # the commission you pay. If you lose the bet you get no money back
        if self.bet_result == match.FTR:
            odds = float(self.bet_price)
            return (odds - 1.0) * (1.0 - commission)
        else:
            return -1.0


# In[47]:

# league_two = league_analysis.year_201516.elt_league
# league_one = league_analysis.year_201516.elo_league
# championship = league_analysis.year_201516.ech_league
# premiership = league_analysis.year_201516.epl_league
# scottish_premiership = league_analysis.year_201516.spl_league


def review_bet_lines(league_bet_lines, start_date, end_date):
    league_profit_loss = 0.0
    total_profit_loss = 0.0
    for league_name, (current_league, bet_lines) in league_bet_lines.items():
        league_profit_loss = 0.0
        if not bet_lines:
            continue
        print('{0}'.format(league_name))
        print()
        for bet_line in bet_lines:
            try:
                match = bet_line.get_relevant_match(current_league, start_date, end_date)
            except IndexError:
                message_template = 'Data not available for match: {0} vs {1}'
                message = message_template.format(bet_line.home, bet_line.away)
                print(message)
                continue
            profit_loss = bet_line.get_profit_loss(match=match, commission=0.05)
            league_profit_loss += profit_loss
            display_bet_analysis(bet_line, match, current_league, profit_loss=profit_loss)
        print('League profit/loss: {0}'.format(league_profit_loss))
        print('------------------------')
        print()
        total_profit_loss += league_profit_loss
    print('Total profit/loss: {0}'.format(total_profit_loss))
    return total_profit_loss


def review_bets_file(bets_filename):
    all_leagues = league_analysis.year_201516.all_leagues
    league_bet_lines = {league.title: (league, [])
                        for league in all_leagues}

    def add_bet_line(bet_line):
        for league in all_leagues:
            home = league_analysis.alias_team(bet_line.home)
            away = league_analysis.alias_team(bet_line.away)
            if home in league.teams and away in league.teams:
                _league, league_lines = league_bet_lines[league.title]
                league_lines.append(bet_line)
                break
        else:
            message = 'Match not found in any league, {0} vs {1}'
            raise Exception(message.format(bet_line.home, bet_line.away))

    with open(bets_filename) as bets_file:
        bets_text = bets_file.read()

    print(bets_filename)
    for line in bets_text.split('\n'):
        if line == '' or line.startswith('#'):
            continue
        if line.startswith('start:'):
            start_date = line.split(' ')[1]
            continue
        if line.startswith('end:'):
            end_date = line.split(' ')[1]
            continue
        bet_line = BetLine(line)
        add_bet_line(bet_line)
    return review_bet_lines(league_bet_lines, start_date, end_date)

def analyse_multiple_bet_files(bet_filenames):
    profit_loss = 0.0
    for filename in bet_filenames:
        profit_loss += review_bets_file(filename)
    print('Total profit/loss: {0}'.format(profit_loss))

if __name__ == '__main__':
    import sys
    import os
    try:
        bets_filenames = [sys.argv[1]]
    except IndexError:
        directory = 'data/1516'
        data_dir_ls = os.listdir(directory)
        bets_filenames = [os.path.join(directory, f)
                          for f in os.listdir(directory)
                          if f.startswith('bets-')]
        print(data_dir_ls)
    analyse_multiple_bet_files(bets_filenames)



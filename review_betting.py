import blog.posts.league_analysis as league_analysis
import collections

def result_count_factory():
    return {'H': 0, 'D': 0, 'A': 0}
    
def post_match_odds(matches):
    sotr_buckets = collections.defaultdict(result_count_factory)
    tsr_buckets = collections.defaultdict(result_count_factory)
    for match in matches:
        sotr_diff = match.HST - match.AST
        sotr_buckets[sotr_diff][match.FTR] += 1
        tsr_diff = match.HS - match.AS
        tsr_buckets[tsr_diff][match.FTR] += 1
    return sotr_buckets, tsr_buckets

sotr_buckets, tsr_buckets = post_match_odds(league_analysis.get_all_matches())

def display_table(headers, rows):
    cell_size = 16
    def pad_cell(s):
        padded_s = s + (' ' * cell_size)
        return(padded_s[:cell_size])
    def print_row(cells):
        cells = [pad_cell(str(c)) for c in cells]
        print("|".join(cells))

    border = '-' * ((cell_size + 1) * len(headers))
    print(border)
    print_row(headers)
    for row in rows:
        print_row(row)
    print(border)


all_leagues = league_analysis.year_201516.all_leagues
class BetLine(object):
    def __init__(self, bet_line):
        """Example Correct Score bet line: Bristol Rovers v Barnet: 1 - 1, 7.0
        Example of a Result bet line: Walsall v Doncaster: Walsall, 1.97
        """
        self.parse_result_line(bet_line)
        for league in all_leagues:
            home = league_analysis.alias_team(self.home)
            away = league_analysis.alias_team(self.away)
            if home in league.teams and away in league.teams:
                self.league = league
                break
        else:
            message = 'Match not found in any league, {0} vs {1}'
            raise Exception(message.format(bet_line.home, bet_line.away))


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
        price_fields = bet_details.split(', ')
        result = price_fields[0]
        if result == "The Draw":
            self.bet_result = 'D'
        elif result == self.home:
            self.bet_result = 'H'
        else:
            assert result == self.away
            self.bet_result = 'A'
        self.bet_price = price_fields[1]
        if len(price_fields) == 4:
            modifier = price_fields[2]
            modifier_name, asian_handicap = modifier.split(' ')
            assert modifier_name == 'Asian'
            self.asian_handicap = float(asian_handicap)
            self.handicapped_team = price_fields[3]
        else:
            self.asian_handicap = 0
            self.handicapped_team = None
    
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
        if self.handicapped_team is None:
            match_result = match.FTR
        else:
            teams = [match.HomeTeam, match.AwayTeam]
            assert self.handicapped_team in teams
            if self.handicapped_team == match.HomeTeam:
                home_goals = self.asian_handicap + match.FTHG
                away_goals = match.FTAG
            else:
                away_goals = self.asian_handicap + match.FTAG
                home_goals = match.FTHG
            if home_goals > away_goals:
                match_result = 'H'
            elif home_goals == away_goals:
                match_result = 'D'
            else:
                assert away_goals > home_goals
                match_result = 'A'
                
            
        if self.bet_result == match_result:
            odds = float(self.bet_price)
            return (odds - 1.0) * (1.0 - commission)
        else:
            return -1.0

    def calculate_post_match_odds(self, shots_ratio):
        match = self.match
        if shots_ratio == "SOTR":
            buckets = sotr_buckets
            difference = match.HST - match.AST
        else:
            assert shots_ratio == "TSR"
            buckets = tsr_buckets
            difference = match.HS - match.AS
        try:
            bucket = buckets[difference]
        except KeyError:
            return None
        total_matches = sum(bucket.values())
        number = bucket[self.bet_result]
        if not number:
            return None
        proportion = float(number) / float(total_matches)
        implied_odds = 1.0 / proportion
        return implied_odds

    def post_match_expected_profit_loss(self, shots_ratio, commission=0.05):
        pm_odds = self.calculate_post_match_odds(shots_ratio)
        if pm_odds is None:
            # Bit of a clutch but this means the odds were essentially
            # off the charts which probably means we lost by a long way,
            # and that the bet was essentially throwing money away.
            return -1.0
        expected_pay_out = (1.0 / pm_odds) * float(self.bet_price)
        expected_profit_loss = (expected_pay_out * (1.0 - commission)) - 1.0
        return expected_profit_loss

    def display_bet_analysis(self):
        match = self.match
        # So this is the number of goals we would have expected the team to have scored based on shots
        home_shots_goals = match.HS / self.league.shots_per_goal
        away_shots_goals = match.AS / self.league.shots_per_goal
        # Similarly for shots on target
        home_sot_goals = match.HST / self.league.sot_per_goal
        away_sot_goals = match.AST / self.league.sot_per_goal

        # Who is closer to the shots scorelines, the bet or the real scoreline?
        home_shots_score_diff = abs(match.FTHG - home_shots_goals)
        away_shots_score_diff = abs(match.FTAG - away_shots_goals)
        home_sots_score_diff = abs(match.FTHG - home_sot_goals)
        away_sots_score_diff = abs(match.FTAG - away_sot_goals)

        profit_loss = self.get_profit_loss()

        sotr_post_match_implied_odds = self.calculate_post_match_odds('SOTR')
        tsr_post_match_implied_odds = self.calculate_post_match_odds('TSR')

        headers = ['', match.HomeTeam, match.AwayTeam]
        rows = [['Goals', match.FTHG, match.FTAG],
                ['Shots', match.HS, match.AS],
                ['SOT', match.HST, match.AST],
                ['Shots Scoreline', home_shots_goals, away_shots_goals],
                ['SOT Scoreline', home_sot_goals, away_sot_goals],
                ['Score-Shots Diff', home_shots_score_diff, away_shots_score_diff],
                ['Score-Sots Diff', home_sots_score_diff, away_sots_score_diff],
                ['Bet', self.bet_result, self.bet_result],
                ['Odds', self.bet_price, self.bet_price],
                ['Profit/Loss', profit_loss, profit_loss],
                ['Implied Sotr', sotr_post_match_implied_odds, sotr_post_match_implied_odds],
                ['Implied TSR', tsr_post_match_implied_odds, tsr_post_match_implied_odds],
                ]
        display_table(headers, rows)


def profit_loss_bet_lines(bet_lines):
    return sum(bl.get_profit_loss() for bl in bet_lines)

def post_match_expected_profit_loss_bet_lines(bet_lines):
    return sum(bl.post_match_expected_profit_loss(bl) for bl in  bet_lines)

def display_bet_lines_analysis(bet_lines):
    for bet_line in bet_lines:
        bet_line.display_bet_analysis()

def read_bets_file(bets_filename):
    with open(bets_filename) as bets_file:
        bets_text = bets_file.read()

    bet_lines = []
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
        try:
            bet_line.get_relevant_match(bet_line.league,
                                        start_date, end_date)
        except IndexError:
            msg_template = 'Data not available for match: {0} vs {1}'
            msg = msg_template.format(bet_line.home, bet_line.away)
            print(msg)
            continue
        bet_lines.append(bet_line)
    return bet_lines

def display_analysis_bets_file(bets_filename):
    bet_lines = read_bets_file(bets_filename)
    display_bet_lines_analysis(bet_lines)

class SummaryTotals(object):
    def __init__(self):
        self.profit_loss = 0.0
        self.sotr_expected_profit_loss = 0.0
        self.tsr_expected_profit_loss = 0.0

def analyse_multiple_bet_files(bet_filenames):
    bet_lines = []
    for bet_filename in bet_filenames:
        bet_lines.extend(read_bets_file(bet_filename))

    leagues_profit_loss = collections.defaultdict(SummaryTotals)
    for bet_line in bet_lines:
        league_summary = leagues_profit_loss[bet_line.league.title]
        profit_loss = bet_line.get_profit_loss()
        league_summary.profit_loss += profit_loss
        sotr_exp_pl = bet_line.post_match_expected_profit_loss('SOTR')
        league_summary.sotr_expected_profit_loss += sotr_exp_pl
        tsr_exp_pl = bet_line.post_match_expected_profit_loss('TSR')
        league_summary.tsr_expected_profit_loss += tsr_exp_pl

    print('-------------------------')
    print('Totals for all bet files analysed:')
    for league_name, summary_totals in leagues_profit_loss.items():
        print('{0}: {1}, {2}, {3}'.format(league_name,
                                          summary_totals.profit_loss,
                                          summary_totals.sotr_expected_profit_loss,
                                          summary_totals.tsr_expected_profit_loss))
    total_profit_loss = sum(st.profit_loss for st in leagues_profit_loss.values())
    total_exp_sotr = sum(st.sotr_expected_profit_loss for st in leagues_profit_loss.values())
    total_exp_tsr = sum(st.tsr_expected_profit_loss for st in leagues_profit_loss.values())
    print('Overall total profit/loss: {0}, {1}, {2}'.format(
            total_profit_loss, total_exp_sotr, total_exp_tsr))

    print('----- Dividing by how you have betted ----------')
    for result in ['H', 'A', 'D']:
        relevant_bets = [bl for bl in bet_lines
                         if bl.bet_result == result]
        profit_loss = sum(bl.get_profit_loss() for bl in relevant_bets)
        sotr_exp = sum(bl.post_match_expected_profit_loss('SOTR') for bl in relevant_bets)
        tsr_exp = sum(bl.post_match_expected_profit_loss('TSR') for bl in relevant_bets)
        print('{0} bets total profit/loss: {1}'.format(result, profit_loss))
        print('    bets total sotr expected profit/loss: {0}'.format(sotr_exp))
        print('    bets total tsr expected profit/loss: {0}'.format(tsr_exp))
        print('    based on {0} bets'.format(len(relevant_bets)))

    print('----- Dividing by how the match ended ----------')
    for result in ['H', 'A', 'D']:
        relevant_bets = [bl for bl in bet_lines
                         if bl.match.FTR == result]
        profit_loss = sum(bl.get_profit_loss() for bl in relevant_bets)
        sotr_exp = sum(bl.post_match_expected_profit_loss('SOTR') for bl in relevant_bets)
        tsr_exp = sum(bl.post_match_expected_profit_loss('TSR') for bl in relevant_bets)
        print('{0} results total profit/loss: {1}'.format(result, profit_loss))
        print('    bets total sotr expected profit/loss: {0}'.format(sotr_exp))
        print('    bets total tsr expected profit/loss: {0}'.format(tsr_exp))
        print('    based on {0} bets'.format(len(relevant_bets)))
    

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
    key_fun = lambda f: league_analysis.last_modified_date(f)
    last_bet_file = max(bets_filenames, key=key_fun)
    display_analysis_bets_file(last_bet_file)
    # Just so we get the totals just for the last bet file
    analyse_multiple_bet_files([last_bet_file])
    analyse_multiple_bet_files(bets_filenames)

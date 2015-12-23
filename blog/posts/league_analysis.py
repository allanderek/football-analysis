"""Takes care of all of the grunt work of obtaining and parsing the
data and fixtures for all of the leagues. We also implement a script to
analyse upcoming fixtures using the past data of the current season.
"""

from IPython.display import display, HTML
import urllib.request
import os
import datetime
import csv
import matplotlib.pyplot as plot
import numpy
import itertools
import collections


# Make the graphs twice as big.
plot.rcParams['savefig.dpi'] = 2 * plot.rcParams['savefig.dpi']


class Match(object):

    """Holds a parsed match object, each line of a data file is parsed
    into one Match object.
    """

    def opponent(self, team):
        if team == self.HomeTeam:
            return self.AwayTeam
        else:
            assert team == self.AwayTeam
            return self.HomeTeam

    def get_quick_title(self):
        return '{0} vs {1}'.format(self.HomeTeam, self.AwayTeam)

    @property
    def home_shots(self):
        return self.HS

    @property
    def away_shots(self):
        return self.AS

    @property
    def home_tsr(self):
        return clean_ratio(self.HS, self.HS + self.AS)

    @property
    def away_tsr(self):
        return clean_ratio(self.AS, self.HS + self.AS)

    @property
    def home_sotr(self):
        return clean_ratio(self.HST, self.HST + self.AST)

    @property
    def away_sotr(self):
        return clean_ratio(self.AST, self.HST + self.AST)

    @property
    def home_target_ratio(self):
        return clean_ratio(self.HST, self.HS + self.HST)

    @property
    def away_target_ratio(self):
        return clean_ratio(self.AST, self.AS + self.AST)

    @property
    def home_booking_points(self):
        return (self.HY * 10) + (self.HR * 25)

    @property
    def away_booking_points(self):
        return (self.AY * 10) + (self.AR * 25)

    @property
    def winning_odds(self):
        return {'H': self.BbAvH, 'A': self.BbAvA, 'D': self.BbAvD}[self.FTR]

int_fields = ['FTHG', 'FTAG', 'HTHG', 'HTAG', 'HS', 'AS', 'HST', 'AST', 'HHW',
              'AHW', 'HC', 'AC', 'HF', 'AF', 'HO', 'AO', 'HY', 'AY', 'HR', 'AR',
              'HBP', 'ABP', 'Bb1X2']

float_fields = ['BbMxH', 'BbAvH', 'BbMxD',
                'BbAvD', 'BbMxA', 'BbAvA']


def create_match(field_names, row):
    match = Match()
    for index, name in enumerate(field_names):
        value = row[index]
        if name in int_fields:
            value = int(value)
        if name in float_fields:
            value = float(value)
        setattr(match, name, value)
    return match


def is_home_game(team, game):
    return team == game.HomeTeam


def is_away_game(team, game):
    return team == game.AwayTeam


def involved_in_game(team, game):
    return is_home_game(team, game) or is_away_game(team, game)


def points_in_game(team, game):
    assert involved_in_game(team, game)
    assert game.FTR in ['H', 'D', 'A']
    if game.FTR == 'H' and is_home_game(team, game):
        return 3
    elif game.FTR == 'A' and is_away_game(team, game):
        return 3
    elif game.FTR == 'D':
        return 1
    else:
        return 0


def stats_for_in_game(team, game, home_stat, away_stat):
    assert involved_in_game(team, game)
    if is_home_game(team, game):
        return home_stat
    else:
        return away_stat


def stats_against_in_game(team, game, home_stat, away_stat):
    # A slightly cheeky way to implement this
    return stats_for_in_game(team, game, away_stat, home_stat)


def shots_for_in_game(team, game):
    return stats_for_in_game(team, game, game.HS, game.AS)


def shots_against_in_game(team, game):
    return stats_against_in_game(team, game, game.HS, game.AS)


def goals_for_in_game(team, game):
    return stats_for_in_game(team, game, game.FTHG, game.FTAG)


def goals_against_in_game(team, game):
    return stats_against_in_game(team, game, game.FTHG, game.FTAG)


def sot_for_in_game(team, game):
    return stats_for_in_game(team, game, game.HST, game.AST)


def sot_against_in_game(team, game):
    return stats_against_in_game(team, game, game.HST, game.AST)


def booking_points_for_in_game(team, game):
    return stats_for_in_game(team, game, game.home_booking_points,
                             game.away_booking_points)


def booking_points_against_in_game(team, game):
    return stats_against_in_game(team, game, game.home_booking_points,
                                 game.away_booking_points)


def yellow_cards_in_game(team, game):
    return stats_for_in_game(team, game, game.HY, game.AY)


def red_cards_in_game(team, game):
    return stats_for_in_game(team, game, game.HR, game.AR)


def get_team_rating(pdo, tsotr, tsr):
    """Essentially tsr * tsott * pdo, but not weight equally, James Grayson
    gives it as: Rating = (0.5+(TSR-0.5)*0.732^0.5) *
                          (1.0+(%TSOTt-1.0)*0.166^2) *
                          (1000+(PDO-1000)*0.176^0.5)
    But we have normalised the three values to average at 0. Note that by
    doing this we really shouldn't multipy. Instead we will add, but we will
    add only 0.82 of tsr, 0.45 of tsott and 0.4 of pdo because these appear
    to be the repeatable portions.
    """
    normalised_tsr = (tsr - 0.5) * 2.0
    rating = (0.82 * normalised_tsr) + (0.45 * tsotr) + (0.4 * pdo)
    return rating


def clean_ratio(sub, total, default=0.0):
    """Returns the ratio of sub to total, assuming that sub is included within
    total. So for example sub may be the shots on target and total may be
    all shots. We return default in the case that total is zero. The default
    likely does not come up much for the stats we're looking at here, you
    would have to have a small sample of games and even then the stats tend
    not to be zero for the total for even a sample of one game. Eg. the
    total number of shots taken is rarely zero for even one game. This is
    just a warning that if you have your default wrongly set, then you
    likely won't notice this and may mess up, say, at the start of the
    season.
    """
    return sub / total if total else default


class TeamStats(object):

    """Note that this is intended to only be used with a set number of games,
    if you change the set of games, then you pretty much have to recalculate
    all of the stats.
    """

    def __init__(self, teamname, games):
        self.teamname = teamname
        self.games = games

        def sum_stat(stat_fun):
            return sum(stat_fun(teamname, game) for game in games)

        self.num_games = len(games)
        self.points = sum_stat(points_in_game)
        self.shots_for = sum_stat(shots_for_in_game)
        self.shots_against = sum_stat(shots_against_in_game)
        total_shots = self.shots_for + self.shots_against
        self.tsr = clean_ratio(self.shots_for, total_shots, default=0.5)
        self.goals_for = sum_stat(goals_for_in_game)
        self.goals_against = sum_stat(goals_against_in_game)
        self.sot_for = sum_stat(sot_for_in_game)
        self.sot_against = sum_stat(sot_against_in_game)
        total_sot = self.sot_for + self.sot_against
        self.sotr = clean_ratio(self.sot_for, total_sot, default=0.5)
        self.sot_for_ratio = clean_ratio(self.sot_for, self.shots_for,
                                         default=0.0)
        self.sot_against_ratio = clean_ratio(self.sot_against,
                                             self.shots_against, default=0.0)
        self.tsotr = self.sot_for_ratio - self.sot_against_ratio
        self.goals_sot_for_ratio = clean_ratio(self.goals_for, self.sot_for,
                                               default=0.0)
        self.goals_sot_against_ratio = clean_ratio(self.goals_against,
                                                   self.sot_against,
                                                   default=0.0)
        self.pdo = self.goals_sot_for_ratio - self.goals_sot_against_ratio
        self.yellows = sum_stat(yellow_cards_in_game)
        self.reds = sum_stat(red_cards_in_game)
        self.booking_points_for = sum_stat(booking_points_for_in_game)
        self.booking_points_against = sum_stat(booking_points_against_in_game)
        self.team_rating = get_team_rating(self.pdo, self.tsotr, self.tsr)

        self.current_unbeaten_run = 0
        self.current_winless_run = 0
        self.current_winning_run = 0
        for game in self.games:
            points = points_in_game(self.teamname, game)
            if points == 3:
                self.current_winning_run += 1
                self.current_unbeaten_run += 1
                self.current_winless_run = 0
            elif points == 1:
                self.current_winning_run = 0
                self.current_unbeaten_run += 1
                self.current_winless_run += 1
            else:
                assert points == 0
                self.current_winning_run = 0
                self.current_unbeaten_run = 0
                self.current_winless_run += 1

    def average_stat(self, stat_name):
        return getattr(self, stat_name) / float(self.num_games)

    def get_stat_from_label(self, label):
        stat_name = label.replace(' ', '_').lower()
        return getattr(self, stat_name)


interesting_stats = ['Shots For', 'Shots Against', 'TSR', 'SOTR', 'Goals For',
                     'Goals Against', 'SOT For', 'SOT Against', 'SOT For Ratio',
                     'SOT Against Ratio', 'TSOTR', 'Goals SOT For Ratio',
                     'Goals SOT Against Ratio', 'PDO', 'Team Rating'
                     ]


def compare_home_away_form(league, team, stat_names=None):
    home_stats = league.home_team_stats[team]
    away_stats = league.away_team_stats[team]
    if stat_names is None:
        stat_names = interesting_stats
    headings = ['Stat', 'Home', 'Away']
    rows = [[s, home_stats.get_stat_from_label(s),
             away_stats.get_stat_from_label(s)]
            for s in stat_names]
    per_game_stats = ['points', 'goals_for', 'goals_against']
    per_game_rows = [[s + "-avg", home_stats.average_stat(s),
                      away_stats.average_stat(s)]
                     for s in per_game_stats]
    display_table(headings, per_game_rows + rows)


def last_modified_date(filepath):
    modification_timestamp = os.path.getmtime(filepath)
    modification_date = datetime.date.fromtimestamp(modification_timestamp)
    return modification_date


def needs_refreshing(filepath):
    """Basically we assume that if the file in question is for a season
    before the current one, then the data has not been updated and we do
    not need to refresh it. If it is from the current season, then we
    check whether we have downloaded the file previously today and if
    not we re-download it. Note, that this assumes the file does exist.
    """
    today = datetime.date.today()
    year = today.year - 2000  # Obviously does not work prior to 2000
    if today.month <= 6:
        current_season = str(year - 1) + str(year)
    else:
        current_season = str(year) + str(year + 1)
    return (current_season in filepath and
            last_modified_date(filepath) != today)


def download_if_stale(filepath, fileurl):
    """Given a file to download we check if there exists a file in
    the filesystem that was downloaded today, if so we do not download
    it again, otherwise we download it afresh.
    """
    if not os.path.exists(filepath) or needs_refreshing(filepath):
        urllib.request.urlretrieve(fileurl, filepath)

# We sometimes call this from within the 'blog/posts' directory and
# sometimes from the parent directory.
data_dir_base = 'data/' if os.path.isdir('data/') else '../../data/'


class League(object):

    def __init__(self, short_title, fixtures_directory, year, title=None):
        self.title = title if title is not None else fixtures_directory
        data_dir_url = 'http://www.football-data.co.uk/mmz4281/' + year
        data_file_basename = short_title + ".csv"
        self.data_url = data_dir_url + '/' + data_file_basename
        self.data_dir = data_dir_base + year
        self.data_file = self.data_dir + '/' + data_file_basename
        fixtures_base_url = "http://www.bbc.co.uk/sport/football/"
        self.fixtures_url = fixtures_base_url + \
            fixtures_directory + "/fixtures"
        self.fixtures_file = "{0}/{1}-fixtures.html".format(self.data_dir,
                                                            short_title)
        self._retrieve_data()
        self._retrieve_fixtures()
        self._parse_league_data()
        self._calculate_statistics()

    def _retrieve_data(self):
        if not os.path.isdir(self.data_dir):
            os.makedirs(self.data_dir)
        download_if_stale(self.data_file, self.data_url)

    def _retrieve_fixtures(self):
        download_if_stale(self.fixtures_file, self.fixtures_url)

    def display_title(self):
        display(HTML("<h2>" + self.title + "</h2>"))

    def _parse_league_data(self):
        with open(self.data_file, newline='') as csvfile:
            cvsreader = csv.reader(csvfile, delimiter=',', quotechar='|')
            self.field_names = next(cvsreader)
            self.matches = []
            for row in cvsreader:
                try:
                    match = create_match(self.field_names, row)
                    self.matches.append(match)
                except ValueError:
                    # Slightly dodgy in that we assume the problem is that
                    # 'football-data' have input the stub of a game without
                    # actually filling in the data yet, as it does.
                    pass
        # We assume you're in the league if you play at least one game, that is
        # you're the home or the away side at least once.
        home_teams = {m.HomeTeam for m in self.matches}
        away_teams = {m.AwayTeam for m in self.matches}
        self.teams = list(home_teams.union(away_teams))

    def get_game(self, home, away, date):
        games = [m for m in self.matches
                 if (is_home_game(home, m) and
                     is_away_game(away, m) and
                     m.Date == date)]
        if len(games) == 1:
            return games[0]
        else:
            return None

    def get_stats(self, filter_fun):
        def get_team_stats(team):
            games = [game for game in self.matches if filter_fun(team, game)]
            return TeamStats(team, games)
        return {team: get_team_stats(team) for team in self.teams}

    def _calculate_statistics(self):
        self.team_stats = self.get_stats(involved_in_game)
        self.home_team_stats = self.get_stats(is_home_game)
        self.away_team_stats = self.get_stats(is_away_game)
        self._calculate_league_shot_stats()

    def _calculate_league_shot_stats(self):
        # Now shot and shots on target per goal.
        def sum_attribute(attr):
            return float(sum(getattr(m, attr) for m in self.matches))

        self.home_goals = sum_attribute('FTHG')
        self.away_goals = sum_attribute('FTAG')
        self.all_goals = self.home_goals + self.away_goals

        self.home_shots = sum_attribute('HS')
        self.away_shots = sum_attribute('AS')
        self.all_shots = self.home_shots + self.away_shots

        self.home_sot = sum_attribute('HST')
        self.away_sot = sum_attribute('AST')
        self.all_sot = self.home_sot + self.away_sot

        self.shots_per_goal = self.all_shots / self.all_goals
        self.sot_per_goal = self.all_sot / self.all_goals

        self.home_spg = self.home_shots / self.home_goals
        self.home_sotpg = self.home_sot / self.home_goals

        self.away_spg = self.away_shots / self.away_goals
        self.away_sotpg = self.away_sot / self.away_goals

    def compare_game_against_opponents(self, home, away, date):
        """ Does not compare against the league average game, but
        compares against the two team's average game. So if the match
        is between Leicester and Arsenal it compares how well Leicester
        have done against Arsenal compared to the average team against
        Arsenal, and vice-versa.
        """
        match = get_match(self, home, away, date)
        home_stats = self.team_stats[match.HomeTeam]
        away_stats = self.team_stats[match.AwayTeam]
        display_table(['Measure',
                       'Average Per Game for',
                       'This game for',
                       'Average Per Game against opponents'],
                      [['{0} Shots'.format(home),
                        home_stats.average_stat('shots_for'),
                        shots_for_in_game(home, match),
                        away_stats.average_stat('shots_against')],
                       ['{0} Shots'.format(away),
                        away_stats.average_stat('shots_for'),
                        shots_for_in_game(away, match),
                        home_stats.average_stat('shots_against')],

                       ['{0} SOT'.format(home),
                        home_stats.average_stat('sot_for'),
                        sot_for_in_game(home, match),
                        away_stats.average_stat('sot_against')],
                       ['{0} SOT'.format(away),
                        away_stats.average_stat('sot_for'),
                        sot_for_in_game(away, match),
                        home_stats.average_stat('sot_against')]])

    def compare_average_team_games(self, home, away, date):
        match = get_match(self, home, away, date)
        home_stats = self.team_stats[match.HomeTeam]
        home_home_stats = self.home_team_stats[match.HomeTeam]
        away_stats = self.team_stats[match.AwayTeam]
        away_away_stats = self.away_team_stats[match.AwayTeam]
        headers = ['Game Type', 'Shots For', 'Shots Against',
                                'SOT For', 'SOT Against']

        def make_row(title, stats):
            return [title,
                    stats.average_stat('shots_for'),
                    stats.average_stat('shots_against'),
                    stats.average_stat('sot_for'),
                    stats.average_stat('sot_against')]
        rows = [['This {0} game'.format(home),
                 shots_for_in_game(home, match),
                 shots_against_in_game(home, match),
                 sot_for_in_game(home, match),
                 sot_against_in_game(home, match)],
                make_row('Avg {0} game'.format(home), home_stats),
                make_row('Avg {0} game'.format(away), away_stats),
                make_row('Avg {0} home game'.format(home),
                         home_home_stats),
                make_row('Avg {0} away game'.format(away),
                         away_away_stats)]
        display_table(headers, rows)


class Year(object):

    def __init__(self, year):
        self.year_name = year
        self.epl_league = League("E0", "premier-league", year)
        self.ech_league = League("E1", "championship", year)
        self.elo_league = League("E2", "league-one", year)
        self.elt_league = League("E3", "league-two", year)
        self.spl_league = League("SC0", "scottish-premiership", year)
        # No shots data for the scottish championship.
        self.all_leagues = [self.epl_league, self.ech_league,
                            self.elo_league, self.elt_league,
                            self.spl_league]

    def get_all_matches(self, leagues=None, filter_fun=None):
        if leagues is None:
            leagues = self.all_leagues
        else:
            leagues = [getattr(self, league) for league in leagues]
        match_lists = (league.matches for league in leagues)
        matches_iter = itertools.chain.from_iterable(match_lists)
        if filter_fun is None:
            return matches_iter
        else:
            return filter(filter_fun, matches_iter)


year_201011 = Year('1011')
year_201112 = Year('1112')
year_201213 = Year('1213')
year_201314 = Year('1314')
year_201415 = Year('1415')
year_201516 = Year('1516')
all_years = [year_201011, year_201112, year_201213,
             year_201314, year_201415, year_201516]
all_leagues = list(itertools.chain.from_iterable(
    y.all_leagues for y in all_years))


current_year = year_201516
epl = current_year.epl_league
championship = current_year.ech_league
league_one = current_year.elo_league
league_two = current_year.elt_league
spl = current_year.spl_league


def get_match(league, home, away, date):
    def filter_fun(match):
        return (match.HomeTeam == home and
                match.AwayTeam == away and match.Date == date)
    return next(m for m in league.matches if filter_fun(m))


def get_matches_between(leagues, home, away):
    def filter_fun(match):
        return (match.HomeTeam in [home, away] and
                match.AwayTeam in [home, away])
    match_lists = (league.matches for league in leagues)
    matches_iter = itertools.chain.from_iterable(match_lists)
    return filter(filter_fun, matches_iter)


def get_all_matches(years=None, leagues=None, filter_fun=None):
    if years is None:
        years = all_years
    match_lists = (year.get_all_matches(leagues=leagues,
                                        filter_fun=filter_fun)
                   for year in years)
    return itertools.chain.from_iterable(match_lists)


def count_matches(filter_fun, matches):
    return len([m for m in matches if filter_fun(m)])


def get_fraction_of_matches(filter_fun, matches=None):
    if matches is None:
        matches = get_all_matches()
    num_matches = 0
    num_filtered = 0
    for m in matches:
        num_matches += 1
        if filter_fun(m):
            num_filtered += 1
    return (num_filtered, num_matches)


def match_to_html(match):
    template = """
    <table>
      <tr><th></th><th>Home</th><th>Away</th></tr>
      <tr><td>Team</td><td>{0}</td><td>{1}</td></tr>
      <tr><td>Goals</td><td>{2}</td><td>{3}</td></tr>
      <tr><td>Shots</td><td>{4}</td><td>{5}</td></tr>
      <tr><td>SOT</td><td>{6}</td><td>{7}</td></tr>
      {8}
    </table>
    """
    if hasattr(match, 'HHW') and hasattr(match, 'AHW'):
        woodwork_tmpl = "<tr><td>Woodwork</td><td>{0}</td><td>{1}</td></tr>"
        woodwork = woodwork_tmpl.format(match.HHW, match.AHW)
    else:
        woodwork = ""
    html = template.format(match.HomeTeam, match.AwayTeam,
                           match.FTHG, match.FTAG,
                           match.HS, match.AS,
                           match.HST, match.AST,
                           woodwork)
    return html


def create_inline_block(html):
    return '<div style="display:inline-block; margin-right:2em;">{0}</div>'.format(html)


def display_pairs(pairs, inline_block=True):
    row_template = "<tr><td>{0}</td><td>{1}</td></tr>"
    rows = [row_template.format(k, e) for k, e in pairs]
    html_rows = "\n".join(rows)
    html = "\n".join(["<table>", html_rows, "</table>"])
    if inline_block:
        html = create_inline_block(html)
    display(HTML(html))


def display_dictionary(dictionary):
    pairs = sorted(dictionary.items(), key=lambda p: p[1], reverse=True)
    display_pairs(pairs)


def html_table(header_data, row_data):
    """Display an ipython table given the headers and the row data."""
    def make_header_cell(s):
        return '<th>{0}</th>'.format(s)

    def make_cell(s):
        return '<td>{0}</td>'.format(s)

    def make_row(s):
        return '<tr>{0}</tr>'.format(s)
    headers = " ".join([make_header_cell(h) for h in header_data])
    header_row = make_row(headers)
    rows = [make_row(" ".join([make_cell(c) for c in row]))
            for row in row_data]
    rows = "\n".join(rows)
    html = '<table>' + header_row + rows + '</table>'
    return html


def display_table(header_data, row_data):
    html = html_table(header_data, row_data)
    display(HTML(html))


def date_from_string(date_string):
    date_fields = date_string.split('/')
    day, month, year = [int(f) for f in date_fields]
    # We allow you to specify the year as a two-digit number, we assume
    # that such a number which is greater than 50 refers to the 20th
    # century and one that is less than 50 refers to the 21st century,
    # it seems unlikely I will still be using this script in 2050. So,
    # 01/02/16 is the first of February 2016
    # 01/02/95 is the first of Feburary 1995
    if year < 50:
        year += 2000
    elif year < 100:
        year += 1900
    return datetime.date(year, month, day)


def html_blocks(blocks):
    inline_blocks = [create_inline_block(b) for b in blocks]
    html = "\n".join(inline_blocks)
    return (HTML(html))


def display_given_matches(matches):
    """Display a given set of matches."""
    html_matches = [match_to_html(m) for m in matches]
    html = html_blocks(html_matches)
    display(html)


def date_in_range(start_date, datestring, end_date):
    date = date_from_string(datestring)
    return start_date <= date and date <= end_date


def get_matches(league, starting_date, ending_date,
                home_team=None, away_team=None, team_involved=None):
    start_date = date_from_string(starting_date)
    end_date = date_from_string(ending_date)

    def filter_fun(m):
        if home_team is not None and m.HomeTeam != home_team:
            return False
        if away_team is not None and m.AwayTeam != away_team:
            return False
        if (team_involved is not None and
                not involved_in_game(team_involved, m)):
            return False
        return date_in_range(start_date, m.Date, end_date)
    matches = [m for m in league.matches if filter_fun(m)]
    return matches


def display_match(league, home_team, away_team, date):

    match = get_match(league, home_team, away_team, date)
    match_html = match_to_html(match)
    title = '{0} {1} - {2} {3}'.format(match.HomeTeam, match.FTHG,
                                       match.FTAG, match.AwayTeam)
    html = '<h1>{0}</h1>{1}'.format(title, match_html)
    display(HTML(html))


def display_matches(league, starting_date, ending_date):
    """Display all matches within a league between the given dates."""
    matches = get_matches(league, starting_date, ending_date)
    display_given_matches(matches)


def display_shots_per_goal_info(years=None):
    if years is None:
        years = all_years

    def get_data_row(league_short_name):
        if league_short_name == 'Overall':
            leagues = [l for y in years for l in y.all_leagues]
        else:
            league_name = league_short_name + '_league'
            leagues = [getattr(y, league_name) for y in years]

        def sum_attribute(attribute):
            return sum(getattr(l, attribute) for l in leagues)

        home_goals = sum_attribute('home_goals')
        away_goals = sum_attribute('away_goals')
        all_goals = sum_attribute('all_goals')

        home_shots = sum_attribute('home_shots')
        home_spg = home_shots / home_goals
        away_shots = sum_attribute('away_shots')
        away_spg = away_shots / away_goals
        all_shots = sum_attribute('all_shots')
        shots_per_goal = all_shots / all_goals

        home_sot = sum_attribute('home_sot')
        home_sotpg = home_sot / home_goals
        away_sot = sum_attribute('away_sot')
        away_sotpg = away_sot / away_goals
        all_sot = sum_attribute('all_sot')
        sot_per_goal = all_sot / all_goals

        return [league_short_name, shots_per_goal, sot_per_goal,
                home_spg, home_sotpg, away_spg, away_sotpg]

    leagues = ['epl', 'ech', 'elo', 'elt', 'spl', 'Overall']
    data_rows = [get_data_row(league) for league in leagues]
    header_row = ['league', 'shots per goal', 'sot per goal',
                  'home spg', 'home sotpg', 'away spg', 'away sotpg']
    display_table(header_row, data_rows)


def collect_after_game_dicts(league, start_date, end_date):
    """Returns a dictionary of dictionaries. The outer dictionary has
    intergers as keys. The integer represents the number of games. The
    value associated with a number of games is a dictionary which maps
    the teams of the league to team stats. So if you want to find out a
    team's statistics after x number of games you call this function and
    then:
        dictionaries = collect_after_game_dicts(...)
        team_stats = dictionaries[x][team]
    'team_stats' will now old a TeamStats object represents the
    statistics for 'team' after 'x' games.
    This method allows you to do things such as plot how a team's stat
    has changed over the course of a season.
    """
    after_game_no_dicts = collections.defaultdict(dict)

    def add_team_stats(team, after_game_no, stat):
        stat_dict = after_game_no_dicts[after_game_no]
        stat_dict[team] = stat

    for team in league.teams:
        matches = get_matches(league, start_date, end_date, team_involved=team)
        for x in range(1, len(matches) + 1):
            stats = TeamStats(team, matches[:x])
            add_team_stats(team, x, stats)

    for x, dictionary in after_game_no_dicts.items():
        if len(dictionary) != len(league.teams):
            del after_game_no_dicts[x]
    return after_game_no_dicts


def get_stats_rankings(stats_dictionary, stat_name):
    pairs = stats_dictionary.items()
    key_fun = lambda p: getattr(p[1], stat_name)
    sorted_pairs = sorted(pairs, key=key_fun, reverse=True)
    return sorted_pairs


def rank_sorted_pairs(sorted_pairs):
    def get_rows(sorted_pairs):
        latest_value = None
        latest_position = None
        for position, (key, value) in enumerate(sorted_pairs, start=1):
            if value == latest_value:
                position = latest_position
                position_string = '-'
            else:
                latest_position = position
                position_string = str(position)
            latest_value = value
            yield [position_string, key, value]
    return get_rows(sorted_pairs)

# TODO: There is definitely some overlap between 'display_ranked_table'
# and 'display_stats_table', but note that display_stats_tables allows
# for more columns than the one that is sorted on.


def create_ranked_table(headers, pairs, reverse=None):
    if reverse is None:
        reverse = True
    sorted_pairs = sorted(pairs, key=lambda r: r[1], reverse=reverse)
    rows = rank_sorted_pairs(sorted_pairs)
    return html_table(['Position'] + headers, rows)


def display_ranked_table(headers, pairs, reverse=None):
    display(HTML(create_ranked_table(headers, pairs, reverse=reverse)))


def display_ranked_tables(tables_data):
    ranked_tables = [create_ranked_table(h, p, r) for h, p, r in tables_data]
    html = html_blocks(ranked_tables)
    display(html)


def rank_teams_single_matches(matches, stat_suffix, stat_header_name=None):
    if stat_header_name is None:
        stat_header_name = stat_suffix

    def get_pairs():
        for match in matches:
            yield (match.HomeTeam, getattr(match, 'home_' + stat_suffix))
            yield (match.AwayTeam, getattr(match, 'away_' + stat_suffix))
    display_ranked_table(['Team', stat_header_name], get_pairs())


def display_stats_table(after_game_no_dicts, stat_names):
    """To get the argument you can simply call the above
    'collect_after_game_dicts', this means that we will give the table
    after a set number of games, which will mean all teams will have
    played the same number. This allows us to give a meaningful table
    for something like 'goals', or 'shots' which are cumulative.
    """
    latest_dict = after_game_no_dicts[len(after_game_no_dicts)]
    first_stat_name = stat_names[0]
    sorted_pairs = get_stats_rankings(latest_dict, first_stat_name)

    def get_rows(sorted_pairs):
        latest_stat = None
        latest_position = None
        for position, (team, stats) in enumerate(sorted_pairs, start=1):
            this_stat = getattr(stats, first_stat_name)
            if latest_stat == this_stat:
                position = latest_position
            else:
                latest_position = position
            stat_cells = [getattr(stats, name) for name in stat_names]
            row = [position, team] + stat_cells
            yield_row
    rows = get_rows(sorted_pairs)
    display_table(['Position', 'Team'] + stat_names, rows)


def display_statistic_rankings(league, stat_name):
    def get_rows(stat_rankings, stat_name):
        latest_stat = None
        for position, (team, stats) in enumerate(stat_rankings, start=1):
            stat = getattr(stats, stat_name)
            position_string = '-' if stat == latest_stat else str(position)
            latest_stat = stat
            row = [position_string, team, stat]
            yield row

    stat_rankings = get_stats_rankings(league.team_stats, stat_name)
    rows = get_rows(stat_rankings, stat_name)
    display_table(['Position', 'Team', stat_name], rows)


def get_stat_pairs(stats_list, stat_name):
    return [(stats.teamname, getattr(stats, stat_name))
            for stats in stats_list]


def blog_weekly_header(league, start_date, end_date):
    weekend_matches = get_matches(league, start_date, end_date)
    display_given_matches(weekend_matches)

    points_pairs = get_stat_pairs(league.team_stats.values(), 'points')
    points_table_data = (['Team', 'Points'], points_pairs, True)

    team_rating_pairs = get_stat_pairs(
        league.team_stats.values(), 'team_rating')
    team_rating_table_data = (['Team', 'Team Rating'], team_rating_pairs, True)

    pdo_pairs = get_stat_pairs(league.team_stats.values(), 'pdo')
    pdo_table_data = (['Team', 'PDO'], pdo_pairs, True)

    tables_data = [points_table_data, team_rating_table_data, pdo_table_data]
    display_ranked_tables(tables_data)

team_line_colors = {'Sunderland': ('DarkGreen', '--'),
                    'Crystal Palace': ('Crimson', '-'),
                    'Southampton': ('Red', '--'),
                    'West Ham': ('MediumTurquoise', '--'),
                    'Liverpool': ('Red', '-'),
                    'West Brom': ('Black', '-'),
                    'Man City': ('LightSkyBlue', '-'),
                    'Chelsea': ('Blue', '-'),
                    'Everton': ('Blue', '--'),
                    'Leicester': ('Blue', ':'),
                    'Swansea': ('Black', '--'),
                    'Watford': ('Gold', '-'),
                    'Man United': ('Red', ':'),
                    'Aston Villa': ('MediumTurquoise', '-'),
                    'Newcastle': ('Black', ':'),
                    'Norwich': ('Gold', '--'),
                    'Tottenham': ('DarkBlue', '-.'),
                    'Arsenal': ('Red', '-.'),
                    'Stoke': ('DarkRed', '-'),
                    'Bournemouth': ('DarkRed', ':')}


def plot_changing_stats(league, after_game_no_dicts,
                        stat_name, teams=None, rankings=False,
                        y_axis_lims=None):
    if teams is None:
        teams = league.teams
    plot.xlabel('Game Number')

    if rankings:
        plot.title('Rank in {0} after game #'.format(stat_name))
        plot.ylabel('Rank in {0}'.format(stat_name))

        def get_team_rank(ranking_table, team_name):
            latest_position = 1
            latest_stat = None
            for position, (team, stats) in enumerate(ranking_table, start=1):
                stat = getattr(stats, stat_name)
                if latest_stat != stat:
                    latest_position = position
                latest_stat = stat
                if team == team_name:
                    return latest_position
            else:
                raise KeyError

        ranking_tables = [get_stats_rankings(d, stat_name)
                          for d in after_game_no_dicts.values()]
        get_ys = lambda team: [get_team_rank(table, team)
                               for table in ranking_tables]
        plot.gca().set_ylim(len(league.teams) + 1, 1)
    else:
        plot.title('{0} after game #'.format(stat_name))
        plot.ylabel(stat_name)
        get_ys = lambda team: [getattr(after_game_no_dicts[x][team],
                                       stat_name)
                               for x in xs]

    if y_axis_lims is not None:
        plot.gca().set_ylim(*y_axis_lims)
    xs = range(1, len(after_game_no_dicts) + 1)
    for team in teams:
        ys = get_ys(team)
        color, line_style = team_line_colors.get(team, (None, None))
        plot.plot(xs, ys, label=team, color=color, linestyle=line_style)
    plot.legend(bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.)
    plot.xticks(xs)
    plot.show()


def scatter_stats(league, title='', xlabel='', ylabel='', teams=None,
                  get_x_stat=None, get_y_stat=None, annotate_teams=None):
    """By default all teams are annotated, to annotate none pass in '[]' as the
    list of teams to annotate.
    """
    if teams is None:
        teams = league.teams
    if annotate_teams is None:
        annotate_teams = league.teams

    plot.title(title)
    plot.xlabel(xlabel)
    plot.ylabel(ylabel)
    xs = []
    ys = []
    for team in teams:
        x_stat = get_x_stat(league, team)
        xs.append(x_stat)
        y_stat = get_y_stat(league, team)
        ys.append(y_stat)
        plot.scatter(x_stat, y_stat)

        if team in annotate_teams:
            plot.annotate(team, xy=(x_stat, y_stat),
                          xytext=(40, -20),
                          textcoords='offset points',
                          ha='right', va='bottom',
                          bbox=dict(boxstyle='round,pad=0.5',
                                    fc='yellow', alpha=0.5),
                          arrowprops=dict(arrowstyle='->',
                                          connectionstyle='arc3,rad=0'))

    coefficients = numpy.polyfit(xs, ys, 1)
    polynomial = numpy.poly1d(coefficients)
    ys = polynomial(xs)
    plot.plot(xs, ys)
    plot.show()
    plot.close()
    display(HTML('line of best fit: ' + str(polynomial)))


def graph_leagues(x_label, y_label, leagues=None, get_x_stat=None,
                  get_y_stat=None, annotate_teams=None):
    """Produce a scatter plot for each team in each of the provided
    leagues. Will error if `leagues` is not specified.
    """
    def get_stat_from_label(label):
        stat_name = label.replace(' ', '_').lower()
        return lambda league, team: getattr(league.team_stats[team], stat_name)
    if get_x_stat is None:
        get_x_stat = get_stat_from_label(x_label)
    if get_y_stat is None:
        get_y_stat = get_stat_from_label(y_label)
    for league in leagues:
        title = '{0}: {1}/{2}'.format(league.title, x_label, y_label)
        scatter_stats(league, title=title,
                      xlabel=x_label, ylabel=y_label,
                      get_x_stat=get_x_stat, get_y_stat=get_y_stat,
                      annotate_teams=annotate_teams
                      )


def scatter_match_stats(matches, xlabel='', ylabel='', title='',
                        get_x_stat=None, get_y_stat=None,
                        annotate=True):
    plot.title(title)
    plot.xlabel(xlabel)
    plot.ylabel(ylabel)
    xs = []
    ys = []
    for match in matches:
        x_stat = get_x_stat(match)
        xs.append(x_stat)
        y_stat = get_y_stat(match)
        ys.append(y_stat)
        plot.scatter(x_stat, y_stat)

        if annotate:
            annotation = match.HomeTeam + ' v ' + match.AwayTeam
            plot.annotate(annotation, xy=(x_stat, y_stat),
                          xytext=(40, -20),
                          textcoords='offset points',
                          ha='right', va='bottom',
                          bbox=dict(boxstyle='round,pad=0.5',
                                    fc='yellow', alpha=0.5),
                          arrowprops=dict(arrowstyle='->',
                                          connectionstyle='arc3,rad=0'))

    coefficients = numpy.polyfit(xs, ys, 1)
    polynomial = numpy.poly1d(coefficients)
    ys = polynomial(xs)
    plot.plot(xs, ys)
    plot.show()
    plot.close()
    display(HTML('line of best fit: ' + str(polynomial)))


def get_adjusted_stat(matches, team, stat_home_name, stat_away_name, reverse_stat_dict):
    matches = [m for m in matches if involved_in_game(team, m)]

    def get_adjusted_stat(match):
        if match.HomeTeam == team:
            opponent = match.AwayTeam
            team_stat = getattr(match, stat_home_name)
        else:
            opponent = match.HomeTeam
            team_stat = getattr(match, stat_away_name)
        opponent_avg_stat = reverse_stat_dict[opponent]
        return team_stat - opponent_avg_stat
    sum_diff = sum(get_adjusted_stat(m) for m in matches)
    diff_per_game = sum_diff / float(len(matches))
    return diff_per_game


def get_adjusted_stat_dictionary(league, stat_home_name,
                                 stat_away_name, reverse_stat_name):
    def get_reverse_stat(team):
        stats = league.team_stats[team]
        return getattr(stats, reverse_stat_name) / float(stats.num_games)
    reverse_stat_dict = {t: get_reverse_stat(t) for t in league.teams}
    adjusted_stats = {t: get_adjusted_stat(league.matches, t,
                                           stat_home_name,
                                           stat_away_name,
                                           reverse_stat_dict)
                      for t in league.teams}
    return adjusted_stats


class BaseAnalyser(object):

    def __init__(self, ignore_matches=None):
        self.leagues = [year.epl_league for year in all_years]
        self.reset_per_league_stats()
        self.ignore_matches = ignore_matches

    def valid_match(self, home_stats, away_stats):
        """Determines whether a match should be evaluated"""
        # If either of the statistics is None then you cannot evaluate the
        # match
        if home_stats is None or away_stats is None:
            return False
        # Otherwise if we have not specified a number of matches to ignore then
        # this match can be evaluated.
        if self.ignore_matches is None:
            return True
        # If we have specified a number of matches to ignore, check both teams
        # have played at least that many:
        if (len(home_stats.games) < self.ignore_matches or
                len(away_stats.games) < self.ignore_matches):
            return False
        return True

    def analyse_matches_with_contemporary_stats(self, league):
        team_stats = dict()

        def update_stats(match, team, stats):
            stats = team_stats.get(team, None)
            if stats is None:
                games = [match]
            else:
                games = stats.games + [match]
            team_stats[team] = TeamStats(team, games)
        for match in league.matches:
            home_stats = team_stats.get(match.HomeTeam, None)
            away_stats = team_stats.get(match.AwayTeam, None)
            if self.valid_match(home_stats, away_stats):
                self.evaluate_match(match, home_stats, away_stats)

            update_stats(match, match.HomeTeam, home_stats)
            update_stats(match, match.AwayTeam, away_stats)

    def reset_per_league_stats(self):
        pass

    def display_per_league_results(self):
        pass

    def analyse_leagues(self):
        for league in self.leagues:
            self.reset_per_league_stats()
            self.analyse_matches_with_contemporary_stats(league)
            self.display_per_league_results()


class HistoricalBetAnalyser(BaseAnalyser):

    def __init__(self, get_bet, commission=0.05, ignore_matches=None):
        self.leagues = [year.epl_league for year in all_years]
        self.get_bet = get_bet
        self.commission = commission
        self.total_profit_loss = 0.0
        self.reset_per_league_stats()
        self.ignore_matches = ignore_matches

    def reset_per_league_stats(self):
        self.counter = {'H': 0, 'A': 0, 'D': 0}
        self.pl_counter = {'H': 0.0, 'A': 0.0, 'D': 0.0}
        self.wins_counter = {'H': 0, 'A': 0, 'D': 0}
        self.league_profit_loss = 0.0

    def match_profit_loss(self, match, bet):
        if bet == match.FTR:
            return (match.winning_odds - 1.0) * (1.0 - self.commission)
        else:
            return -1.0

    def evaluate_match(self, match, home_stats, away_stats):
        bet = self.get_bet(match, home_stats, away_stats)
        if bet is None:
            return
        self.counter[bet] += 1

        profit_loss = self.match_profit_loss(match, bet)
        self.pl_counter[bet] += profit_loss
        if profit_loss > 0.0:
            self.wins_counter[bet] += 1
        self.league_profit_loss += profit_loss
        self.total_profit_loss += profit_loss

    def display_per_league_results(self):
        print("League profit/loss: {0}".format(self.league_profit_loss))
        for result in ['H', 'D', 'A']:
            msg_format = "{0} bets wins {1} out of {2} for profit/loss: {3}"
            print(msg_format.format(result, self.wins_counter[result],
                                    self.counter[result],
                                    self.pl_counter[result]))

    def display_results(self):
        print('Total profit loss for all leagues: {0}'.format(
            self.total_profit_loss))

    def historical_betting(self, get_bet):
        self.analyse_leagues()
        self.display_results()


def result_count_factory():
    return {'H': 0, 'D': 0, 'A': 0}


class HistoricalStatAnalyser(BaseAnalyser):

    def __init__(self, stat_name):
        self.leagues = all_leagues
        self.reset_per_league_stats()
        self.buckets = collections.defaultdict(result_count_factory)
        # [-1.0, -0.9 ... 0.0, 0.1, ... 1.0]
        self.bucket_keys = [x / 10.0 for x in range(-10, 10)]
        self.ignore_matches = 4
        self.stat_name = stat_name

    def reset_per_league_stats(self):
        pass

    def get_bucket(self, diff):
        for bucket in self.bucket_keys:
            if diff < bucket:
                return bucket
        else:
            assert False

    def get_stat_diff(self, home_stats, away_stats):
        return (getattr(home_stats, self.stat_name) -
                getattr(away_stats, self.stat_name))

    def evaluate_match(self, match, home_stats, away_stats):
        stat_diff = self.get_stat_diff(home_stats, away_stats)
        bucket = self.get_bucket(stat_diff)
        self.buckets[bucket][match.FTR] += 1

    def display_per_league_results(self):
        pass

    def display_results(self):
        for bucket in self.bucket_keys:
            result_counts = self.buckets[bucket]
            print('Bucket {0} to {1}'.format(bucket - 0.1, bucket))
            total_matches = sum(r for r in result_counts.values())
            if total_matches == 0:
                (print('no such matches'))
                continue
            proportions = self.get_proportions(result_counts)
            for result in ['H', 'D', 'A']:
                number = result_counts[result]
                proportion = proportions[result]
                print("          '{0}': {1}, {2}".format(
                    result, number, proportion))

    def get_proportions(self, result_counts):
        total_matches = sum(r for r in result_counts.values())

        return {result: float(result_counts[result]) / float(total_matches)
                for result in result_counts.keys()}

    def get_reasonable_result_counts(self, stat_diff):
        """ Just gets the bucket related to the stat_diff, however,
        if the bucket has fewer than 100 results, we get the closest bucket
        that has 100 or more results """
        result_counts = self.buckets[self.get_bucket(stat_diff)]
        num_results = sum(result_counts.values())
        if num_results < 100:
            if stat_diff < 0:
                new_stat_diff = stat_diff + 0.1
            else:
                new_stat_diff = stat_diff - 0.1
            return self.get_reasonable_result_counts(new_stat_diff)
        return result_counts

    def get_implied_odds(self, home_stats, away_stats):
        stat_diff = self.get_stat_diff(home_stats, away_stats)
        result_counts = self.get_reasonable_result_counts(stat_diff)
        proportions = self.get_proportions(result_counts)
        implied_odds = {r: 1.0 / p for r, p in proportions.items()}
        return implied_odds

    def historically_bet(self):
        def get_bet(match, home_stats, away_stats):
            implied_odds = self.get_implied_odds(home_stats, away_stats)
            differences = [(r, getattr(match, 'BbAv' + r) - implied_odds[r])
                           for r in ['H', 'A', 'D']]
            sorted_differences = sorted(
                differences, reverse=True, key=lambda p: p[1])
            bet, gain = sorted_differences[1]
            if gain > 0.0:
                return bet
            else:
                return None
        self.historical_betting(get_bet)

from bs4 import BeautifulSoup
# The teams on the left here, that is the keys of the dictionary are
# team names from sources other than the data files. So in particular
# from the fixture list, but also betfair etc. The idea is that we can
# lookup a team name from any source in the data files by first using
# this dictionary via 'alias_team'.
team_aliases = {'Dundee Utd': 'Dundee United',
                'Inverness CT': 'Inverness C',
                'Partick Thistle': 'Partick',
                'Man Utd': 'Man United',
                'Sheff Wed': 'Sheffield Weds',
                'Nottm Forest': "Nott'm Forest",
                'Sheff Utd': 'Sheffield United',
                'MK Dons': 'Milton Keynes Dons',
                'Fleetwood': 'Fleetwood Town',
                'Peterborough': 'Peterboro',
                'Crawley': 'Crawley Town',
                'Newport': 'Newport County',
                'Dag & Red': 'Dag and Red',
                'Oxford Utd': 'Oxford',
                'Wimbledon': 'AFC Wimbledon',
                'Bristol Rovers': 'Bristol Rvs',
                'Cambridge Utd': 'Cambridge',
                'York City': 'York',
                'Notts Co': 'Notts County',
                'Accrington S': 'Accrington',
                'C Palace': 'Crystal Palace',
                'Ross Co': 'Ross County',
                }


def alias_team(team):
    return team_aliases.get(team, team)


def get_match_teams(match_details):
    home_team_span = match_details.find('span', class_='team-home teams')
    home_team = home_team_span.a.contents[0]
    away_team_span = match_details.find('span', class_='team-away teams')
    away_team = away_team_span.a.contents[0]
    return (alias_team(home_team), alias_team(away_team))


month_strings = {'January': 1,
                 'February': 2,
                 'March': 3,
                 'April': 4,
                 'May': 5,
                 'June': 6,
                 'July': 7,
                 'August': 8,
                 'September': 9,
                 'October': 10,
                 'November': 11,
                 'December': 12}


def fixtures_date_on_or_before(datestring, date):
    # An example datestring 'Saturday 9th April 2016'
    fields = [f for f in datestring.split(' ') if f not in ['', '\n']]
    day_string = fields[1]
    day = int(day_string[:len(day_string) - 2])
    month = month_strings[fields[2]]
    year = int(fields[3])
    return datetime.date(year, month, day) <= date


def get_fixtures(fixtures_page, end_date):
    with open(fixtures_page, encoding='utf-8') as fixtures_file:
        soup = BeautifulSoup(fixtures_file)
    dates = soup.find_all('h2', class_='table-header')
    fixtures = []
    for date in dates:
        if fixtures_date_on_or_before(date.string, end_date):
            table = date.next_sibling.next_sibling
            match_details_list = table.find_all('td', class_='match-details')
            matches = [get_match_teams(md) for md in match_details_list]
            fixtures.extend(matches)
        else:
            break
    return fixtures


def last_x_matches(league, team, x):
    matches = [m for m in league.matches if involved_in_game(team, m)]
    start_index = max(0, len(matches) - x)
    matches = matches[start_index:]
    for match in matches:
        output_template = '    {0}/{1}/{2}/{3} vs {4}/{5}/{6}/{7}'
        output = output_template.format(match.HomeTeam, match.FTHG,
                                        match.HS, match.HST,
                                        match.AwayTeam, match.FTAG,
                                        match.AS, match.AST)
        print(output)


count_dict = dict()
count_dict['H'] = 0
count_dict['A'] = 0
count_dict['D'] = 0


def analyse_fixtures(league, end_date, stat_analysers):
    fixtures = get_fixtures(league.fixtures_file, end_date)
    fixtures = [(alias_team(h), alias_team(a)) for h, a in fixtures]

    adjusted_shots_for_per_game = get_adjusted_stat_dictionary(
        league, 'HS', 'AS', 'shots_against')
    adjusted_shots_against_per_game = get_adjusted_stat_dictionary(
        league, 'AS', 'HS', 'shots_for')

    def get_adjusted_tsr(team):
        shots_for = adjusted_shots_for_per_game[team]
        shots_against = adjusted_shots_against_per_game[team]
        return shots_for - shots_against

    adjusted_sot_for_per_game = get_adjusted_stat_dictionary(
        league, 'HST', 'AST', 'sot_against')
    adjusted_sot_against_per_game = get_adjusted_stat_dictionary(
        league, 'AST', 'HST', 'sot_for')

    def get_adjusted_sotr(team):
        shots_for = adjusted_sot_for_per_game[team]
        shots_against = adjusted_sot_against_per_game[team]
        return shots_for - shots_against

    def get_avg_adjusted_stat(stats, stat_name):
        opponents = (match.opponent(stats.teamname) for match in stats.games)
        opponents_stats = [
            getattr(league.team_stats[opp], stat_name) for opp in opponents]
        avg_opp_stat = sum(opponents_stats) / len(opponents_stats)
        team_stat = getattr(stats, stat_name)
        adj_stat = team_stat + avg_opp_stat - 0.5
        return adj_stat

    for home_team, away_team in fixtures:
        def print_statline(attribute):
            home = getattr(home_stats, attribute)
            away = getattr(away_stats, attribute)
            print('    {0}: {1} vs {2}'.format(attribute, home, away))
        home_stats = league.team_stats[home_team]
        home_stats.adjsr = get_adjusted_tsr(home_team)
        home_stats.adjsotr = get_adjusted_sotr(home_team)
        away_stats = league.team_stats[away_team]
        away_stats.adjsr = get_adjusted_tsr(away_team)
        away_stats.adjsotr = get_adjusted_sotr(away_team)

        home_stats.avgadjtsr = get_avg_adjusted_stat(home_stats, 'tsr')
        home_stats.avgadjsotr = get_avg_adjusted_stat(home_stats, 'sotr')
        away_stats.avgadjtsr = get_avg_adjusted_stat(away_stats, 'tsr')
        away_stats.avgadjsotr = get_avg_adjusted_stat(away_stats, 'sotr')

        suggested_bet = 'D'
        adjsr_diff = home_stats.adjsr - away_stats.adjsr
        adjsotr_diff = home_stats.adjsotr - away_stats.adjsotr

        if adjsr_diff > 1.5 and adjsotr_diff > 0.68:
            suggested_bet = 'H'
        elif adjsr_diff < -2.5 and adjsotr_diff < -1.1:
            suggested_bet = 'A'

        home_bet_threshold = 2.4 - adjsotr_diff
        away_bet_threshold = 4.4 + adjsotr_diff

        avgadjtsr_diff = home_stats.avgadjtsr - away_stats.avgadjtsr
        avgadjsotr_diff = home_stats.avgadjsotr - away_stats.avgadjsotr
        home_sotr_odds = 1.0 / (max(0.2, 0.45 + avgadjsotr_diff))
        away_sotr_odds = 1.0 / (max(0.1, 0.25 - (0.8 * avgadjsotr_diff)))
        if avgadjsotr_diff > -0.2 and avgadjsotr_diff < 0.1:
            draw_probability = 0.27
        else:
            draw_probability = 0.2
        draw_sotr_odds = 1.0 / draw_probability

        # Team Rating stuff
        tr_analyser = stat_analysers['team_rating']
        tr_implied_odds = tr_analyser.get_implied_odds(home_stats, away_stats)

        print('{0} vs {1}'.format(home_team, away_team))
        last_x_matches(league, home_team, 3)
        last_x_matches(league, away_team, 3)
        print_statline('points')
        print_statline('tsr')
        # print_statline('adjsr')
        print_statline('avgadjtsr')
        print_statline('sotr')
        # print_statline('adjsotr')
        print_statline('avgadjsotr')
        print_statline('pdo')
        print_statline('tsotr')
        print_statline('team_rating')
        # print("    Adj TSR diff = {0}".format(avgadjtsr_diff))
        # print("    Adj Sotr diff = {0}".format(avgadjsotr_diff))
        print("    home_sotr_odds: {0}".format(home_sotr_odds))
        print("    away_sotr_odds: {0}".format(away_sotr_odds))
        print("    draw_sotr_odds: {0}".format(draw_sotr_odds))
        print("    home_tr_odds: {0}".format(tr_implied_odds['H']))
        print("    away_tr_odds: {0}".format(tr_implied_odds['A']))
        print("    draw_tr_odds: {0}".format(tr_implied_odds['D']))


if __name__ == '__main__':
    import sys
    try:
        date_string = sys.argv[1]
        date = date_from_string(date_string)
    except IndexError:
        date = datetime.date.today() + datetime.timedelta(days=3)

    tr_analyser = HistoricalStatAnalyser('team_rating')
    tr_analyser.analyse_leagues()

    stat_analysers = {'team_rating': tr_analyser}
    for league in reversed(current_year.all_leagues):
        print(league.title)
        analyse_fixtures(league, date, stat_analysers)

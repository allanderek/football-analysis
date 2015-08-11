from IPython.display import display, HTML
import urllib.request
import csv
import matplotlib.pyplot as plot
import numpy


class League(object):
    def __init__(self, short_title, fixtures_directory, title=None):
        self.title = title if title is not None else fixtures_directory
        data_dir_url = "http://www.football-data.co.uk/mmz4281/1415/"
        data_file_basename = short_title + ".csv"
        self.data_url = data_dir_url + data_file_basename
        self.data_file = "data/1415/" + data_file_basename
        fixtures_base_url = "http://www.bbc.co.uk/sport/football/"
        self.fixtures_url = fixtures_base_url + fixtures_directory + "/fixtures"
        self.fixtures_file = "data/1415/{0}-fixtures.html".format(short_title)

    def retrieve_data_and_fixtures(self):
        urllib.request.urlretrieve(self.data_url, self.data_file)
        urllib.request.urlretrieve(self.fixtures_url, self.fixtures_file)

    def display_title(self):
        display(HTML("<h2>" + self.title + "</h2>"))

epl_league = League("E0", "premier-league")
ech_league = League("E1", "championship")
elo_league = League("E2", "league-one")
elt_league = League("E3", "league-two")
spl_league = League("SC0", "scottish-premiership")
# League("SC1", "scottish-championship") No shots data
all_leagues = [epl_league, ech_league, elo_league, elt_league, spl_league]


for league in all_leagues:
    league.retrieve_data_and_fixtures()


class Match(object):
    pass
int_fields = ['FTHG', 'FTAG', 'HTHG', 'HTAG', 'HS', 'AS', 'HST', 'AST', 'HHW',
              'AHW', 'HC', 'AC', 'HF', 'AF', 'HO', 'AO', 'HY', 'AY', 'HR', 'AR',
              'HBP', 'ABP']


def create_match(field_names, row):
    match = Match()
    for index, name in enumerate(field_names):
        value = row[index]
        if name in int_fields:
            value = int(value)
        setattr(match, name, value)
    return match


def parse_league_data(league):
    with open(league.data_file, newline='') as csvfile:
        cvsreader = csv.reader(csvfile, delimiter=',', quotechar='|')
        league.field_names = next(cvsreader)
        league.matches = [create_match(league.field_names, row)
                          for row in cvsreader]
    # We assume if you're never the home team, you're not in the league
    league.teams = list({m.HomeTeam for m in league.matches})

for league in all_leagues:
    parse_league_data(league)


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


def get_team_rating(pdo, tsotr, tsr):
    """ Essentially tsr * tsott * pdo, but not weight equally, James Grayson
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
    """ Returns the ratio of sub to total, assuming that sub is included within
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
    """ Note that this is intended to only be used with a set number of games,
        if you change the set of games, then you pretty much have to recalculate
        all of the stats.
    """
    def __init__(self, teamname, games):
        self.teamname = teamname
        self.games = games

        def sum_stat(stat_fun):
            return sum(stat_fun(teamname, game) for game in games)

        self.points = sum_stat(points_in_game)
        self.shots_for = sum_stat(shots_for_in_game)
        self.shots_against = sum_stat(shots_against_in_game)
        total_shots = self.shots_for + self.shots_against
        self.tsr = clean_ratio(self.shots_for, total_shots, default=0.5)
        self.goals_for = sum_stat(goals_for_in_game)
        self.goals_against = sum_stat(goals_against_in_game)
        self.sot_for = sum_stat(sot_for_in_game)
        self.sot_against = sum_stat(sot_against_in_game)
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
        self.team_rating = get_team_rating(self.pdo, self.tsotr, self.tsr)

interesting_stats = ['Shots For', 'Shots Against', 'TSR', 'Goals For',
                     'Goals Against', 'SOT For', 'SOT Against', 'SOT For Ratio',
                     'SOT Against Ratio', 'TSOTR', 'Goals SOT For Ratio',
                     'Goals SOT Against Ratio', 'PDO', 'Team Rating'
                     ]


def get_stats(team, games, filter_fun):
    return TeamStats(team, [g for g in games if filter_fun(team, g)])

for league in all_leagues:
    league.team_stats = {t: get_stats(t, league.matches, involved_in_game)
                         for t in league.teams}
    league.home_team_stats = {t: get_stats(t, league.matches, is_home_game)
                              for t in league.teams}
    league.away_team_stats = {t: get_stats(t, league.matches, is_away_game)
                              for t in league.teams}


def scatter_stats(league, title='', xlabel='', ylabel='',
                  get_x_stat=None, get_y_stat=None, annotate_teams=None):
    """By default all teams are annotated, to annotate none pass in '[]' as the
       list of teams to annotate.
    """
    if annotate_teams is None:
        annotate_teams = league.teams

    plot.title(title)
    plot.xlabel(xlabel)
    plot.ylabel(ylabel)
    xs = []
    ys = []
    for team in league.teams:
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


def graph_leagues(x_label, y_label, leagues=None,
                  get_x_stat=None, get_y_stat=None, annotate_teams=None):
    """This only works if the x/y stats are attributes of a TeamStat object."""
    def get_stat_from_label(label):
        stat_name = label.replace(' ', '_').lower()
        return lambda league, team: getattr(league.team_stats[team], stat_name)
    if get_x_stat is None:
        get_x_stat = get_stat_from_label(x_label)
    if get_y_stat is None:
        get_y_stat = get_stat_from_label(y_label)
    if leagues is None:
        leagues = all_leagues
    for league in leagues:
        title = '{0}: {1}/{2}'.format(league.title, x_label, y_label)
        scatter_stats(league, title=title,
                      xlabel=x_label, ylabel=y_label,
                      get_x_stat=get_x_stat, get_y_stat=get_y_stat,
                      annotate_teams=annotate_teams
                      )

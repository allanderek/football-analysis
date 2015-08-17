from IPython.display import display, HTML
import urllib.request
import os
import csv
import matplotlib.pyplot as plot
import numpy
import itertools


# Make the graphs twice as big.
plot.rcParams['savefig.dpi'] = 2 * plot.rcParams['savefig.dpi']


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


class League(object):
    def __init__(self, short_title, fixtures_directory, year, title=None):
        self.title = title if title is not None else fixtures_directory
        data_dir_url = 'http://www.football-data.co.uk/mmz4281/' + year
        data_file_basename = short_title + ".csv"
        self.data_url = data_dir_url + '/' + data_file_basename
        self.data_dir = '../../data/' + year
        self.data_file = self.data_dir + '/' + data_file_basename
        fixtures_base_url = "http://www.bbc.co.uk/sport/football/"
        self.fixtures_url = fixtures_base_url + fixtures_directory + "/fixtures"
        self.fixtures_file = "{0}/{1}-fixtures.html".format(self.data_dir,
                                                            short_title)

    def retrieve_data(self):
        if not os.path.isdir(self.data_dir):
            os.makedirs(self.data_dir)
        urllib.request.urlretrieve(self.data_url, self.data_file)

    # You should pretty much never wish to retrieve the fixtures without also
    # retrieving the data for that league. By not providing a
    # 'retrieve_fixtures' method, we make it less likely that you update the
    # fixtures and make some analysis of those fixtures whilst forgetting to
    # update the data upon which that analysis is dependent.
    def retrieve_fixtures_and_data(self):
        self.retrieve_data()
        urllib.request.urlretrieve(self.fixtures_url, self.fixtures_file)

    def display_title(self):
        display(HTML("<h2>" + self.title + "</h2>"))

    def parse_league_data(self):
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

    def calculate_statistics(self):
        self.team_stats = self.get_stats(involved_in_game)
        self.home_team_stats = self.get_stats(is_home_game)
        self.away_team_stats = self.get_stats(is_away_game)


class Year(object):
    def __init__(self, year):
        self.epl_league = League("E0", "premier-league", year)
        self.elo_league = League("E2", "league-one", year)
        self.ech_league = League("E1", "championship", year)
        self.elt_league = League("E3", "league-two", year)
        self.spl_league = League("SC0", "scottish-premiership", year)
        # No shots data for the scottish championship.
        self.all_leagues = [self.epl_league, self.ech_league, self.elo_league,
                            self.elt_league, self.spl_league]

    def retrieve_data(self):
        for league in self.all_leagues:
            league.retrieve_data()

    def retrieve_fixtures_and_data(self):
        for league in self.all_leagues:
            league.retrieve_fixtures_and_data()

    def parse_data(self):
        for league in self.all_leagues:
            league.parse_league_data()

    def calculate_statistics(self):
        for league in self.all_leagues:
            league.calculate_statistics()

    def get_all_matches(self):
        match_lists = (league.matches for league in self.all_leagues)
        return itertools.chain.from_iterable(match_lists)

year_201011 = Year('1011')
year_201112 = Year('1112')
year_201213 = Year('1213')
year_201314 = Year('1314')
year_201415 = Year('1415')
year_201516 = Year('1516')
all_years = [year_201011, year_201112, year_201213,
             year_201314, year_201415, year_201516]

# For convenience we retrieve the data for the current year's leagues and
# we set parse all the data for all years, assuming that they are up-to-date,
# which will be true in most cases.
current_year = year_201516
current_year.retrieve_fixtures_and_data()
for year in all_years:
    year.parse_data()
epl = current_year.epl_league
championship = current_year.ech_league
league_one = current_year.elo_league
league_two = current_year.elt_league
spl = current_year.spl_league


def get_all_matches(years=None):
    if years is None:
        years = all_years
    match_lists = (year.get_all_matches() for year in years)
    return itertools.chain.from_iterable(match_lists)


def count_matches(filter_fun, matches):
    return len([m for m in matches if filter_fun(m)])


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
    hhw = match.HHW if hasattr(match, 'HHW') else 'n/a'
    ahw = match.AHW if hasattr(match, 'AHW') else 'n/a'
    html = template.format(match.HomeTeam, match.AwayTeam,
                           match.FTHG, match.FTAG,
                           match.HS, match.AS,
                           match.HST, match.AST,
                           woodwork)
    return html


def display_pairs(pairs):
    row_template = "<tr><td>{0}</td><td>{1}</td></tr>"
    rows = [row_template.format(k, e) for k, e in pairs]
    html_rows = "\n".join(rows)
    html = "\n".join(["<table>", html_rows, "</table>"])
    display(HTML(html))


def date_on_or_before(first_date, second_date):
    """ Returns true if the first date is on or before the second date. """
    first_day, first_month, first_year = first_date.split('/')
    second_day, second_month, second_year = second_date.split('/')
    if first_year < second_year:
        return True
    elif first_year == second_year:
        if first_month < second_month:
            return True
        elif first_month == second_month:
            return first_day <= second_day
    return False


def display_given_matches(matches):
    """ Display a given set of matches """
    def inline_div_match(match):
        inline_block = '<div style="display:inline-block;">{0}</div>'
        return inline_block.format(match_to_html(match))
    match_blocks = [inline_div_match(match) for match in matches]
    html = "\n".join(match_blocks)
    display(HTML(html))


def display_matches(league, starting_date, ending_date):
    """ Display all matches within a league between the given dates """
    def filter_fun(m):
        return (date_on_or_before(starting_date, m.Date) and
                date_on_or_before(m.Date, ending_date))
    matches = [m for m in league.matches if filter_fun(m)]
    display_given_matches(matches)


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


def scatter_match_stats(matches, xlabel='', ylabel='', title='',
                        get_x_stat=None, get_y_stat=None):
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

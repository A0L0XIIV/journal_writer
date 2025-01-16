import os
import psycopg2
import re
import time
from configparser import ConfigParser
from enum import IntEnum
from datetime import datetime, timedelta
from tabulate import tabulate

_CONFIG_FILE_PATH = 'B:\\\\Projects\\journal_writer'
_CONFIG_FILE_NAME = 'config.ini'
_CONFIG_FILE = os.path.join(os.getcwd(), f'{_CONFIG_FILE_PATH}/{_CONFIG_FILE_NAME}')
_CONFIG_SECTION = 'postgresql'
# TODO encrypt the journal text
# Store the journal text globally, just in case it gets lost
journal = ''

# TV show duration regex pattern --> S1E10-S1E13
TV_SERIES_REGEX_PATTERN = r'S([1-9]\d*)E([1-9]\d*)-S([1-9]\d*)E([1-9]\d*)'
# Date regex
DATE_REGEX = r'^\d{4}-\d{2}-\d{2}$'


class EntertaintmentType(IntEnum):
    BOOK = 1
    GAME = 2
    MOVIE = 3
    SERIES = 4
    AUDIOBOOK = 5
    LEGO = 6


class Happiness(IntEnum):
    YORUM_YOK = 0
    BERBAT_OTESI = 1
    BERBAT = 2
    KOTU = 3
    BIRAZ_KOTU = 4
    NORMAL = 5
    FENA_DEGIL = 6
    GAYET_IYI = 7
    BAYA_IYI = 8
    SAHANE = 9
    MUHTESEM = 10


def set_cmd_window_size(cols, lines):
    command = f'mode con: cols={cols} lines={lines}'
    os.system(command)

# --- DB CONNECTION --------------------------------------------

def load_config(filename: str = _CONFIG_FILE, section: str = _CONFIG_SECTION) -> dict[str, str]:
    parser = ConfigParser()
    parser.read(filename)
    config = {}
    if parser.has_section(section):
        params = parser.items(section)
        for param in params:
            config[param[0]] = param[1]
    else:
        raise Exception(f'Section {section} not found in the {filename} file')
    return config

def connect(config: dict[str, str]):
    """
    Connect to the PostgreSQL database server
    """
    try:
        # connecting to the PostgreSQL server
        with psycopg2.connect(
            host=config['host'],
            database=config['database'],
            user=config['user'],
            password=config['password'],
            #connect_timeout=10
        ) as conn:
            print('Connected to the PostgreSQL server.')
            return conn
    except (psycopg2.DatabaseError, Exception) as error:
        print(error)

def query(conn, sql, fetch=True, add_header=False, count=0):
    try:
        conn.autocommit = True
        cursor = conn.cursor()

        cursor.execute(sql)
        if fetch:
            results = [[desc[0] for desc in cursor.description]] if add_header else []
            results.extend(cursor.fetchall())
            # print_query_table(results)

        conn.commit()

        if fetch:
            return results
    except psycopg2.OperationalError:
        # Try again with new conn, got lots of connection errors lately
        count += 1
        if count <= 5:
            print(f'Trying again... #{count}')
            query(connect(config), sql, fetch, add_header, count)
        else:
            print('Tried 5 times, stopped')
    except Exception as e:
        print(e)
        # Maybe it works this time
        if yes_no_question('Try again with a new connection?'):
            query(connect(config), sql, fetch, add_header)

# --- DB QUERY FUNCTIONS ---------------------------------------

def insert_entertainment(conn):
    print(tabulate([(e.name, e.value) for e in EntertaintmentType], tablefmt="rounded_outline"))

    while True:
        _type = typed_input('Type', [int])
        if _type not in iter(EntertaintmentType):
            print('Invalid type!')
        else:
            break
    name = input('Name: ')
    url = input('Image URL: ')
    sql = f"INSERT INTO entertainments (type, name, image_url) VALUES ({_type}, '{name}', '{url}');"
    query(conn, sql, fetch=False)

def get_entertainment(conn, just_show: bool = False) -> tuple[str, int]:
    name = input('Name of the entertainment: ')
    sql = f"SELECT id, name, type FROM entertainments WHERE name ILIKE '%{name}%';"
    entertainments = query(conn, sql)
    if not entertainments or len(entertainments) == 0:
        print('Could not find any entertainments with that name')
        return None, None

    # Print option and return the selected ones ID
    print('0- Nope/Exit')
    for index, ent in enumerate(entertainments):
        print('{i}- {name}'.format(i=index+1, name=ent[1]))

    # Just to show the names, no inputs
    if just_show:
        return None, None
    
    while True:
        selected = typed_input('Select', [int])
        if selected < 0 or selected > len(entertainments):
            print('Invalid selection, try again')
            continue
        elif selected == 0:
            return None, None
        else:
            # ID is the first item of the query (id, name)
            selected_row = entertainments[selected - 1]
            return selected_row[0], selected_row[2]

def add_daily_entertainments() -> list[tuple[str, str, str]]:
    # Daily entertainments to insert
    daily_entertainments = []
    while True:
        if not yes_no_question('Add entertainment?'):
            break
        e_id, e_type = get_entertainment(conn=conn)
        if e_id:
            # It's a TV series, find the last duration
            if e_type == EntertaintmentType.SERIES:
                duration_sql = f"""
                SELECT duration
                FROM daily_entertainments
                WHERE entertainment_id='{e_id}'
                ORDER BY date_created DESC
                LIMIT 1;
                """
                last_duration = query(conn, duration_sql)
                # Make it easy to add a duration for a TV show
                if last_duration and len(last_duration):
                    # It's a list of tuple: [('S1E10-S1E10',)]
                    last_duration = last_duration[0][0]
                    # Parse its numbers
                    match = re.match(TV_SERIES_REGEX_PATTERN, last_duration)
                    if match:
                        season_start = int(match.group(1))
                        episode_start = int(match.group(2))
                        season_end = int(match.group(3))
                        episode_end = int(match.group(4))
                    else:
                        print(f'[ERROR] Duration parse error for {last_duration}')
                        continue

                    # If the season is the same, just get the last episode number
                    if yes_no_question('Same season?'):
                        number_of_episodes = typed_input('How many episodes?', [int])
                        # If it's just 1 episode, start and end numbers should match, that's why we need a -1 at the end
                        duration = f'S{season_end}E{episode_end}-S{season_end}E{episode_end + number_of_episodes - 1}'
                    elif yes_no_question('Next season?'):
                        number_of_episodes = typed_input('How many episodes (from episode 1)?', [int])
                        # If it's just 1 episode, should be like S4E15-S5E1
                        duration = f'S{season_end}E{episode_end}-S{season_end + 1}E{number_of_episodes}'
                    else:
                        duration = input(f'Last duration: {last_duration}, enter duration: ')
                # No last duration
                elif yes_no_question('New series?'):
                    number_of_episodes = typed_input('How many episodes (from session 1 episode 1)?', [int])
                    # If it's just 1 episode, should be like S1E1-S1E1
                    duration = f'S1E1-S1E{number_of_episodes}'
                # Something custom I guess
                else:
                    duration = input('Custom duration: ')

                # Validate duration for TV shows
                if re.match(TV_SERIES_REGEX_PATTERN, duration) is None:
                    print('Invalid TV Series duration, skipping...')
                    continue
            else:
                # TODO convert hour duration to minutes at some point. Needs a DB migration as well!
                duration = typed_input('Duration', [int, float])
            
            print(f'Duration: {duration}')
            daily_entertainments.append(f"((SELECT id FROM new_journal), '{e_id}', '{duration}')")
    return daily_entertainments

def insert_gunluk(conn, is_custom_date = False):
    print(tabulate([(e.name, e.value) for e in Happiness], tablefmt="rounded_outline"))

    # Ewww!
    while True:
        work_happiness = typed_input('Work happiness', [int])
        if work_happiness not in iter(Happiness):
            print('Invalid happiness!')
        else:
            break
    while True:
        daily_happiness = typed_input('Daily (outside work) happiness', [int])
        if daily_happiness not in iter(Happiness):
            print('Invalid happiness!')
        else:
            break
    while True:
        total_happiness = typed_input('Total happiness', [int])
        if total_happiness not in iter(Happiness):
            print('Invalid happiness!')
        else:
            break

    _temp_journal = ''
    _journal_input_msg = 'Journal: '
    while True:
        _temp_journal += input(_journal_input_msg)
        # Ask if it's completed or accidently pressed the Enter button
        if yes_no_question('Is it done?'):
            # Query needs double quote --> ''
            journal = _temp_journal.replace('\'', '\'\'')
            break
        elif yes_no_question('Reset the written text?'):
            _temp_journal = ''
        else:
            # Add the last entry to the input msg, so I can continue writing it seamlessly
            _journal_input_msg += _temp_journal

    # Get daily entertainments
    daily_entertainments = add_daily_entertainments()
    # Remove incorrect ones
    if yes_no_question('Remove any daily entertainments before insert?'):
        while True:
            try:
                if not daily_entertainments:
                    print('No daily entertainments')
                    break
                [print(f'{i}: {de}') for i, de in enumerate(daily_entertainments)]
                remove_index = typed_input('Enter an index to remove, <0 to exit', [int])
                if remove_index < 0:
                    break
                del daily_entertainments[remove_index]
                print(f'Index {remove_index} removed')
            except Exception as e:
                print(f'[ERROR] {e}')
                continue

    if is_custom_date:
        while True:
            query_date = input('Journal date (YYYY-MM-DD): ')
            # Check validity
            if re.match(DATE_REGEX, query_date):
                # Add quotes for timestamp to text casting
                query_date = "'" + query_date + "'"
                break
            else:
                print('Invalid date!')
    else:
        # Adjust the date
        current_hour = datetime.now().hour
        print(f'Current hour: {current_hour}')
        # Defaults to psql's now function
        query_date = 'now()'
        # After 0 / 12 AM, ask to use yesterday as date
        if 0 <= current_hour and current_hour < 4:
            yesterday = datetime.now() - timedelta(days=1)
            _temp_date = datetime.strftime(yesterday, '%Y-%m-%d') + ' 23:59:59.000000-04:00'
            if yes_no_question(f'Use yesterday {_temp_date} as date?'):
                # It's a text, requires ''
                query_date = "'" + _temp_date + "'"

    journal_sql = f"""
    INSERT INTO journals
    (user_id, date, work_happiness, daily_happiness, total_happiness, content)
    VALUES(
        '699082b4-1821-4b46-af07-2df20fc41c5f',
        {query_date},
        {work_happiness},
        {daily_happiness},
        {total_happiness},
        '{journal}'
    )
    RETURNING id
    """

    sql = journal_sql if not daily_entertainments else f"""
    WITH new_journal AS ({journal_sql})

    INSERT INTO daily_entertainments
    (journal_id, entertainment_id, duration)
    VALUES {', '.join(daily_entertainments)}
    """
    # Finish the query
    sql += ';'

    query(conn, sql, fetch=False)

def show_last_10(conn):
    sql = """
    SELECT date, work_happiness, daily_happiness, total_happiness, content, name, duration, type
    FROM daily_entertainments AS d
    RIGHT JOIN journals AS j ON j.id=d.journal_id
    LEFT JOIN entertainments AS e ON e.id=d.entertainment_id
    ORDER BY date DESC LIMIT 10;
    """
    results = query(conn, sql, add_header=True)
    print_query_table(results)

def change_last_daily_entertainment_to_today(conn):
    # First find the entertainment by its name
    e_id = None
    while not e_id:
        e_id, _type = get_entertainment(conn=conn)

    today = datetime.strftime(datetime.now(), '%Y-%m-%d')
    # First try to find it on yesterday's journal
    yesterday = datetime.now() - timedelta(days=1)
    yesterday = datetime.strftime(yesterday, '%Y-%m-%d')
    sql = f"""
    SELECT de.id FROM daily_entertainments AS de
    INNER JOIN journals AS j ON j.id = de.journal_id
    WHERE entertainment_id = '{e_id}' AND j.date::TEXT LIKE '%{yesterday}%';
    """
    result = query(conn, sql)

    if result and len(result) > 0:
        sql = f"""
        SELECT id, date FROM journals
        WHERE date::TEXT LIKE '%{today}%';
        """
        journal_result = query(conn, sql)
        # Check if today's journal isn't there
        if not journal_result or len(journal_result) == 0:
            print('Could not find today\'s journal')
        else:
            sql = f"""
            UPDATE daily_entertainments
            SET journal_id = '{journal_result[0][0]}'
            WHERE id = '{result[0][0]}'
            RETURNING *;
            """
            query(conn, sql)
            print('Move successful')
            show_last_10(conn)

    elif yes_no_question('Could not find it on yesterday, find the last one and move it instead?'):
        sql = f"""
        SELECT de.id, j.id, j.date FROM daily_entertainments AS de
        INNER JOIN journals AS j ON j.id = de.journal_id
        INNER JOIN entertainments AS e ON e.id = de.entertainment_id
        WHERE entertainment_id = '{e_id}'
        ORDER BY j.date DESC LIMIT 1';
        """
        latest_result = query(conn, sql)
        # Check if latest journal isn't there
        if not latest_result and len(latest_result) == 0:
            print('Could not find any latest journal')
        else:
            # List of row tuples to single row tuple
            latest_result = latest_result[0]
            if yes_no_question(f'The latest date is {latest_result[2]}, move it to today?'):
                sql = f"""
                UPDATE daily_entertainments
                SET journal_id = '{latest_result[1]}'
                WHERE id = '{latest_result[0]}'
                RETURNING *;
                """
                query(conn, sql)
                print('Move successful')
                show_last_10(conn)

# --- INPUT/OUTPUT ---------------------------------------------

def print_query_table(results, cut=36):
    """
    Trims the long column data and print results as table (with the first row being the header)
    results: str[][], query results
    cut: int, trim the longer strings after this length, 36 is the UUID length
    """
    printable = []
    for row in results:
        printable.append([cell[:cut] + '...'  if cut > 0 and isinstance(cell, str) and len(cell) > cut else cell for cell in row])
    print(tabulate(printable, headers='firstrow', tablefmt='simple_grid'))

def yes_no_question(text: str) -> bool:
    while True:
        selection = input(f'{text} [y/n]: ')
        if selection.lower() == 'y':
            return True
        elif selection.lower() == 'n':
            return False
        else:
            print('[ERROR] Invalid selection, try again')

def typed_input(msg: str, types: list[type]):
    # TODO accept and handle enums as well!
    while True:
        _input = input(f'{msg}: ')
        for _type in types:
            try:
                return _type(_input)
            except:
                pass
        print('[ERROR] Invalid input type, try again')

# --- MAIN -----------------------------------------------------

if __name__ == '__main__':    
    # Set the window size (adjust as needed)
    set_cmd_window_size(150, 75)

    print('Starting...')
    config = load_config()
    print('Configs loadded')
    sleep_period = 2
    while True:
        conn = connect(config)
        if not conn:
            print(f'Could not connect to DB! Will try again in {sleep_period} seconds...')
            time.sleep(sleep_period)
            sleep_period += 2
        else:
            print('Connected to DB')
            break
    option = ''

    while option != '0':
        try:
            print(tabulate([
                (0, 'Exit'),
                (1, 'Insert a gunluk'),
                (2, 'Insert a gunluk with a custom date'),
                (3, 'Insert an entertainment'),
                (4, 'Find an entertainment'),
                (5, 'Show last 10 with entertainment'),
                (6, 'Custom query'),
                (7, 'Move last entertainment to today'),
                (8, 'Show journal text'),
                ], tablefmt="rounded_outline"))
            option = typed_input('--> ', [int])

            match option:
                case 0:
                    break
                case 1:
                    insert_gunluk(conn)
                    show_last_10(conn)
                case 2:
                    insert_gunluk(conn, is_custom_date=True)
                    show_last_10(conn)
                case 3:
                    insert_entertainment(conn)
                case 4:
                    get_entertainment(conn, just_show=True)
                case 5:
                    show_last_10(conn)
                case 6:
                    q = input('Query: ')
                    r = query(conn, q, add_header=True)
                    if r:
                        # Only 1 column, ask the text cut length
                        if len(r[0]) == 1:
                            l = input('Table cut length (0 to skip): ')
                            print_query_table(r, int(l))
                        else:
                            print_query_table(r)
                case 7:
                    change_last_daily_entertainment_to_today(conn)
                case 8:
                    print(journal)
                case _:
                    print('[ERROR] Invalid input number (0-8)')
        except Exception as e:
            print(e)

    conn.close()
    print('Closed the postgres connection')

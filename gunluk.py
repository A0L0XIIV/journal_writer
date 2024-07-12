import os
import psycopg2
import re
from configparser import ConfigParser
from enum import IntEnum
from datetime import datetime, timedelta
from tabulate import tabulate

_CONFIG_FILE_PATH = 'B:\\\\gunluk\\'
_CONFIG_FILE_NAME = 'config.ini'
_CONFIG_FILE = os.path.join(os.getcwd(), f'{_CONFIG_FILE_PATH}/{_CONFIG_FILE_NAME}')
_CONFIG_SECTION = 'postgresql'
# TODO encrypt the journal text
# Store the journal text globally, just in case it gets lost
journal = ''

# TV show duration regex pattern --> S1E10-S1E13
TV_SERIES_REGEX_PATTERN = '^(S[1-9][0-9]*E[1-9][0-9]*-S[1-9][0-9]*E[1-9][0-9]*)$'


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

def query(conn, sql, fetch=True, add_header=False):
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
    except Exception as e:
        print(e)

def insert_entertainment(conn):
    print(tabulate([(e.name, e.value) for e in EntertaintmentType], tablefmt="rounded_outline"))

    while True:
        _type = input('Type: ')
        if not _type.isdigit() or int(_type) not in iter(EntertaintmentType):
            print('Invalid type!')
        else:
            break
    name = input('Name: ')
    url = input('Image URL: ')
    sql = """
    INSERT INTO entertainments (type, name, image_url) VALUES ({0}, '{1}', '{2}');
    """.format(_type, name, url)
    query(conn, sql, fetch=False)

def get_entertainment(conn) -> tuple[str, int]:
    name = input('Name of the entertainment: ')
    sql = f"SELECT id, name, type FROM entertainments WHERE name ILIKE '%{name}%';"
    entertainments = query(conn, sql)
    if not entertainments or len(entertainments) == 0:
        print('Could not find any entertainments with that name')
        return

    # Print option and return the selected ones ID
    print('0- Nope/Exit')
    for index, ent in enumerate(entertainments):
        print('{i}- {name}'.format(i=index+1, name=ent[1]))
    while True:
        selected = input('Select: ')
        if not selected.isdigit():
            print('Invalid selection, must be int!')
        selected = int(selected)
        if selected < 0 or selected > len(entertainments):
            print('Invalid selection, try again')
        elif selected == '0':
            break
        else:
            # ID is the first item of the query (id, name)
            selected_index = int(selected) - 1
            selected_row = entertainments[selected_index]
            return selected_row[0], selected_row[2]

def insert_gunluk(conn, is_custom_date = False):
    print(tabulate([(e.name, e.value) for e in Happiness], tablefmt="rounded_outline"))

    # Ewww!
    while True:
        work_happiness = input('Work happiness: ')
        if not work_happiness.isdigit() or int(work_happiness) not in iter(Happiness):
            print('Invalid happiness!')
        else:
            break
    while True:
        daily_happiness = input('Daily (outside work) happiness: ')
        if not daily_happiness.isdigit() or int(daily_happiness) not in iter(Happiness):
            print('Invalid happiness!')
        else:
            break
    while True:
        total_happiness = input('Total happiness: ')
        if not total_happiness.isdigit() or int(total_happiness) not in iter(Happiness):
            print('Invalid happiness!')
        else:
            break

    _temp_journal = ''
    while True:
        _temp_journal += input('Journal: ')
        # Ask if it's completed or accidently pressed the Enter button
        if input('Is it done? (y, n): ') == 'y':
            # Query needs double quote --> ''
            journal = _temp_journal.replace('\'', '\'\'')
            break
        elif input('Reset the written text? (y, n): ') == 'y':
            _temp_journal = ''


    daily_entertainments = []
    while True:
        if input('Add entertainment? (y, n): ').lower() == 'n':
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
                to_show = None
                # Make it easy to add a duration for a TV show
                if last_duration and len(last_duration):
                    # It's a list of tuple: [('S1E10-S1E10',)]
                    last_duration = last_duration[0][0]
                    # If the season is the same, just get the last episode number
                    if input("Same season (y, n)?") == 'y':
                        initial, last = last_duration.split('-')
                        # Fint the initial and last 'E', and get the numbers index (+1)
                        initial_episode_index = initial.rfind('E') + 1
                        last_episode_index = last.rfind('E') + 1
                        # Find the last episode number and increase it by 1
                        new_episode = int(last[last_episode_index:]) + 1
                        # Construct the final string ==> S5E14-S5E17 ==> S5E + 18 + - + S5E + [INPUT]
                        to_show = f'{initial[:initial_episode_index]}{new_episode}-{last[:last_episode_index]}'
                        duration = to_show + input('Duration: ' + to_show)
                    else:
                        # TODO get the last session, +1, use E1
                        print(f'Last duration: {last_duration}')
                # Skip this if it's already filled
                if to_show is None:
                    duration = input('Duration: ')
                # Validate duration for TV shows
                if re.match(TV_SERIES_REGEX_PATTERN, duration) is None:
                    print('Invalid TV Series duration, skipping...')
                    continue
            else:
                duration = input('Duration: ')
            daily_entertainments.append(f"((SELECT id FROM new_journal), '{e_id}', '{duration}')")

    if is_custom_date:
        query_date = input('Journal date (YYYY-MM-DD): ')
        # Add quotes for timestamp to text casting
        query_date = "'" + query_date + "'"
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
            if input('Use yesterday {} as date? (y, n): '.format(_temp_date)) == 'y':
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
            WHERE id = '{result[0][0]}';
            """
            query(conn, sql)
            print('Move successful')
            show_last_10(conn)

    elif input('Could not find it on yesterday, find the last one and move it instead? (y, n): ') == 'y':
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
            if input(f'The latest date is {latest_result[2]}, move it to today? (y, n): ') == 'y':
                sql = f"""
                UPDATE daily_entertainments
                SET journal_id = '{latest_result[1]}'
                WHERE id = '{latest_result[0]}';.
                """
                query(conn, sql)
                print('Move successful')
                show_last_10(conn)

def print_query_table(results, cut=36):
    """
    Trims the long column data and print results as table (with the first row being the header)
    results: str[][], query results
    cut: int, trim the longer strings after this length, 36 is the UUID length
    """
    printable = []
    for row in results:
        printable.append([cell[:cut] + '...'  if isinstance(cell, str) and len(cell) > cut else cell for cell in row])
    print(tabulate(printable, headers='firstrow', tablefmt='simple_grid'))

if __name__ == '__main__':
    print('Starting...')
    config = load_config()
    print('Configs loadded')
    conn = connect(config)
    if not conn:
        print('Could not connect to DB!')
        exit()
    option = ''

    while option != '0':
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
        option = input('--> ')

        if option == '0':
            break
        elif option == '1':
            insert_gunluk(conn)
            show_last_10(conn)
        elif option == '2':
            insert_gunluk(conn, is_custom_date=True)
            show_last_10(conn)
        elif option == '3':
            insert_entertainment(conn)
        elif option == '4':
            get_entertainment(conn)
        elif option == '5':
            show_last_10(conn)
        elif option == '6':
            q = input('Query: ')
            r = query(conn, q, add_header=True)
            if r:
               print_query_table(r)
        elif option == '7':
            change_last_daily_entertainment_to_today(conn)
        elif option == '8':
            print(journal)
        else:
            print('ERROR: Invalid input')

    conn.close()
    print('Closed the postgres connection')

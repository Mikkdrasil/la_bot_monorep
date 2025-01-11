"""Script does several things:
1. checks if the first posts of the searches were changed
2. FIXME - checks active searches' status (Ищем, НЖ, НП, etc.)
3. checks active searches' visibility (accessible for everyone, restricted to a certain group or permanently deleted).
Updates are either saved in PSQL or send via pub/sub to other scripts"""

import datetime
import hashlib
import json
import logging
import re
import urllib.request

import google.auth.transport.requests
import google.cloud.logging
import google.oauth2.id_token
import requests
import sqlalchemy  # idea for optimization – to move to psycopg2
from google.cloud import pubsub_v1, secretmanager

url = 'http://metadata.google.internal/computeMetadata/v1/project/project-id'
req = urllib.request.Request(url)
req.add_header('Metadata-Flavor', 'Google')
project_id = urllib.request.urlopen(req).read().decode()

client = secretmanager.SecretManagerServiceClient()
requests_session = requests.Session()
publisher = pubsub_v1.PublisherClient()

log_client = google.cloud.logging.Client()
log_client.setup_logging()

bad_gateway_counter = 0


class Search:
    def __init__(self, topic_id=None):
        self.topic_id = topic_id


class PercentGroup:
    def __init__(
        self,
        n=None,
        start_percent=None,
        finish_percent=None,
        start_num=None,
        finish_num=None,
        frequency=None,
        first_delay=None,
        searches=None,  # noqa
    ):
        searches = []
        self.n = n
        self.sp = start_percent
        self.fp = finish_percent
        self.sn = start_num
        self.fn = finish_num
        self.f = frequency
        self.d = first_delay
        self.s = searches

    def __str__(self):
        days = f' or {int(self.f // 1440)} day(s)' if self.f >= 1440 else ''
        return (
            f'N{self.n: <2}: {self.sp}%–{self.fp}%. Updated every {self.f} minute(s){days}. '
            f'First delay = {self.d} minutes. nums {self.sn}-{self.fn}. num of searches {len(self.s)}'
        )


def get_secrets(secret_request):
    """get GCP secret"""

    name = f'projects/{project_id}/secrets/{secret_request}/versions/latest'
    response = client.access_secret_version(name=name)

    return response.payload.data.decode('UTF-8')


def sql_connect():
    """connect to PSQL in GCP"""

    db_user = get_secrets('cloud-postgres-username')
    db_pass = get_secrets('cloud-postgres-password')
    db_name = get_secrets('cloud-postgres-db-name')
    db_conn = get_secrets('cloud-postgres-connection-name')
    db_socket_dir = '/cloudsql'

    db_config = {
        'pool_size': 5,
        'max_overflow': 0,
        'pool_timeout': 0,  # seconds
        'pool_recycle': 120,  # seconds
    }

    pool = sqlalchemy.create_engine(
        sqlalchemy.engine.url.URL(
            'postgresql+pg8000',
            username=db_user,
            password=db_pass,
            database=db_name,
            query={'unix_sock': '{}/{}/.s.PGSQL.5432'.format(db_socket_dir, db_conn)},
        ),
        **db_config,
    )
    pool.dialect.description_encoding = None

    return pool


def publish_to_pubsub(topic_name, message):
    """publish a new message to pub/sub"""

    topic_path = publisher.topic_path(project_id, topic_name)
    message_json = json.dumps(
        {
            'data': {'message': message},
        }
    )
    message_bytes = message_json.encode('utf-8')

    try:
        publish_future = publisher.publish(topic_path, data=message_bytes)
        publish_future.result()  # Verify the publishing succeeded
        logging.info(
            f'Pub/sub message to topic {topic_name} with event_id = {publish_future.result()} has '
            f'been triggered. Content: {message}'
        )

    except Exception as e:
        logging.info(f'Not able to send pub/sub message: {message}')
        logging.exception(e)

    return None


def notify_admin(message):
    """send the pub/sub message to Debug to Admin"""

    publish_to_pubsub('topic_notify_admin', message)

    return None


def define_topic_visibility_by_content(content):
    """define visibility for the topic's content: regular, hidden or deleted"""

    if content.find('Запрошенной темы не существует.') > -1:
        visibility = 'deleted'
    elif content.find('Для просмотра этого форума вы должны быть авторизованы') > -1:
        visibility = 'hidden'
    else:
        visibility = 'regular'

    return visibility


def define_topic_visibility_by_topic_id(search_num):
    """check is the existing search was deleted or hidden"""

    content, site_unavailable = parse_search(search_num)

    if site_unavailable:
        return None, None

    topic_visibility = define_topic_visibility_by_content(content)

    logging.info(f'visibility for search {search_num} is defined as {topic_visibility}')

    return site_unavailable, topic_visibility


def update_one_topic_visibility(search_id):
    """record in psql the visibility of one topic: regular, deleted or hidden"""

    forum_unavailable, visibility = define_topic_visibility_by_topic_id(search_id)
    logging.info(f'Visibility checked for {search_id}: visibility = {visibility}')

    if forum_unavailable or not visibility:
        return None

    pool = sql_connect()
    with pool.connect() as conn:
        try:
            stmt = sqlalchemy.text("""DELETE FROM search_health_check WHERE search_forum_num=:a;""")
            conn.execute(stmt, a=search_id)

            stmt = sqlalchemy.text("""INSERT INTO search_health_check (search_forum_num, timestamp, status)
                                      VALUES (:a, :b, :c);""")
            conn.execute(stmt, a=search_id, b=datetime.datetime.now(), c=visibility)

            logging.info(f'Visibility updated for {search_id} and set as {visibility}')
            logging.info('---------------')

        except Exception as e:
            logging.info('exception in update_one_topic_visibility')
            logging.exception(e)

        conn.close()
    pool.dispose()

    return None


def update_visibility_for_one_hidden_topic():
    """check if the hidden search was unhidden"""

    global requests_session

    pool = sql_connect()
    conn = pool.connect()

    try:
        hidden_topic = conn.execute("""
            SELECT h.search_forum_num, s.status
            FROM search_health_check AS h LEFT JOIN searches AS s
            ON h.search_forum_num=s.search_forum_num
            WHERE h.status = 'hidden' ORDER BY RANDOM() LIMIT 1;
            /*action='get_one_hidden_topic' */;""").fetchone()

        hidden_topic_id = int(hidden_topic[0])
        current_status = hidden_topic[1]
        if current_status in {'Ищем', 'Возобновлен'}:
            logging.info(f'we start checking visibility for topic {hidden_topic_id}')
            update_one_topic_visibility(hidden_topic_id)

    except Exception as e:
        logging.info('exception in update_visibility_for_one_hidden_topic')
        logging.exception(e)

    conn.close()
    pool.dispose()

    return None


def parse_search(search_num):
    """parse the whole search page"""

    global requests_session
    global bad_gateway_counter

    try:
        url = f'https://lizaalert.org/forum/viewtopic.php?t={search_num}'
        r = requests_session.get(url, timeout=10)  # seconds – not sure if it is efficient in this case
        content = r.content.decode('utf-8')
        content = None if content.find('502 Bad Gateway') > 0 else content
        site_unavailable = False if content else True

    except (requests.exceptions.ReadTimeout, Exception) as e:
        logging.info(f'[che_posts]: site unavailable: {e.__class__.__name__}')
        content = None
        site_unavailable = True

    return content, site_unavailable


def make_api_call(function: str, data: dict) -> dict:
    """makes an API call to another Google Cloud Function"""

    # function we're turing to "title_recognize"
    endpoint = f'https://europe-west3-lizaalert-bot-01.cloudfunctions.net/{function}'

    # required magic for Google Cloud Functions Gen2 to invoke each other
    audience = endpoint
    auth_req = google.auth.transport.requests.Request()
    id_token = google.oauth2.id_token.fetch_id_token(auth_req, audience)
    headers = {'Authorization': f'Bearer {id_token}', 'Content-Type': 'application/json'}

    r = requests.post(endpoint, json=data, headers=headers)
    content = r.json()

    return content


def get_status_from_content_and_send_to_topic_management(topic_id, act_content):
    """block to check if Status of the search has changed – if so send a pub/sub to topic_management"""

    # get the Title out of page content (intentionally avoid BS4 to make pack slimmer)
    pre_title = re.search(r'<h2 class="topic-title"><a href=.{1,500}</a>', act_content)
    pre_title = pre_title.group() if pre_title else None
    pre_title = re.search(r'">.{1,500}</a>', pre_title[32:]) if pre_title else None
    title = pre_title.group()[2:-4] if pre_title else None

    if not title:
        return None

    # language=regexp
    patterns = [[r'(?i)(^\W{0,2}|(?<=\W))(пропал[аи]?\W{1,3})', 'Ищем']]

    status = None
    for pattern in patterns:
        if re.search(pattern[0], title):
            status = pattern[1]
            break

    if not status:
        try:
            data = {'title': title, 'reco_type': 'status_only'}
            title_reco_response = make_api_call('title_recognize', data)

            if title_reco_response and 'status' in title_reco_response.keys() and title_reco_response['status'] == 'ok':
                title_reco_dict = title_reco_response['recognition']
                if 'status' in title_reco_dict.keys():
                    status = title_reco_dict['status']
            else:
                title_reco_dict = {'topic_type': 'UNRECOGNIZED'}

            logging.info(f'{title_reco_dict=}')

        except Exception as ex:
            logging.exception(ex)
            notify_admin(repr(ex))

    if not status or status == 'Ищем':
        return None

    publish_to_pubsub('topic_for_topic_management', {'topic_id': topic_id, 'status': status})

    return None


def update_first_posts_and_statuses():
    """update first posts for topics"""

    def get_list_of_topics():
        """get best list of searches for which first posts should be checked"""

        base_table_of_objects = []

        pool_2 = sql_connect()
        conn_2 = pool_2.connect()

        try:
            raw_sql_extract = conn_2.execute("""
                WITH
                s AS (SELECT search_forum_num, search_start_time, forum_folder_id FROM searches
                    WHERE status = 'Ищем'),
                h AS (SELECT search_forum_num, status FROM search_health_check),
                f AS (SELECT folder_id, folder_type FROM geo_folders
                    WHERE folder_type IS NULL OR folder_type = 'searches')

                SELECT s.search_forum_num, s.search_start_time FROM s
                LEFT JOIN h ON s.search_forum_num=h.search_forum_num
                JOIN f ON s.forum_folder_id=f.folder_id
                WHERE (h.status != 'deleted' AND h.status != 'hidden') or h.status IS NULL
                ORDER BY 2 DESC
                /*action='get_list_of_searches_for_first_post_and_status_update 3.0' */
                ;""").fetchall()

            # form the list-like table
            if raw_sql_extract:
                for line_2 in raw_sql_extract:
                    new_object = Search(topic_id=line_2[0])
                    base_table_of_objects.append(new_object)

        except Exception as e2:
            logging.info('exception in get_list_of_searches_for_first_post_update')
            logging.exception(e2)

        conn_2.close()
        pool_2.dispose()

        return base_table_of_objects

    def generate_list_of_topic_groups():
        """generate N search groups, groups needed to define which part of all searches will be checked now"""

        percent_step = 5
        list_of_groups = []
        current_percent = 0

        while current_percent < 100:
            n = int(current_percent / percent_step)
            new_group = PercentGroup(
                n=n,
                start_percent=current_percent,
                finish_percent=min(100, current_percent + percent_step - 1),
                frequency=2**n,
                first_delay=2 ** (n - 1) - 1 if n != 0 else 0,
            )
            list_of_groups.append(new_group)
            current_percent += percent_step

        return list_of_groups

    def define_which_topic_groups_to_be_checked(list_of_groups):
        """gives an output of 2 groups that should be checked for this time"""

        start_time = datetime.datetime(2023, 1, 1, 0, 0, 0)
        curr_minute = int(((datetime.datetime.now() - start_time).total_seconds() / 60) // 1)

        curr_minute_list = []
        for group_2 in list_of_groups:
            if not ((curr_minute - group_2.d) % group_2.f):
                curr_minute_list.append(group_2)
                logging.info(f'Group to be checked {group_2}')

        return curr_minute_list

    def enrich_groups_with_topics(list_of_groups, list_of_s):
        """add searches to the chosen groups"""

        num_of_searches = len(list_of_s)

        for group_2 in list_of_groups:
            group_2.sn = int((group_2.sp * num_of_searches / 100) // 1)
            group_2.fn = min(int(((group_2.fp + 1) * num_of_searches / 100) // 1 - 1), len(list_of_s))

        for j, search in enumerate(list_of_s):
            for group_2 in list_of_groups:
                if group_2.sn <= j <= group_2.fn:
                    group_2.s.append(search)

        return list_of_groups

    def prettify_content(content):
        """remove the irrelevant code from the first page content"""

        # TODO - seems can be much simplified with regex
        # cut the wording of the first post
        start = content.find('<div class="content">')
        content = content[(start + 21) :]

        # find the next block and limit the content till this block
        next_block = content.find('<div class="back2top">')
        content = content[: (next_block - 12)]

        # cut out div closure
        fin_div = content.rfind('</div>')
        content = content[:fin_div]

        # cut blank symbols in the end of code
        finish = content.rfind('>')
        content = content[: (finish + 1)]

        # exclude dynamic info – views of the pictures
        patterns = re.findall(r'\) \d+ просмотр(?:а|ов)?', content)
        if patterns:
            for word in patterns:
                content = content.replace(word, ')')

        # exclude dynamic info - token / creation time / sid / etc / footer
        patterns_list = [
            r'value="\S{10}"',
            r'value="\S{32}"',
            r'value="\S{40}"',
            r'sid=\S{32}&amp;',
            r'всего редактировалось \d+ раз.',  # AK:issue#9
            r'<span class="footer-info"><span title="SQL time:.{120,130}</span></span>',
        ]

        patterns = []
        for pat in patterns_list:
            patterns += re.findall(pat, content)

        if patterns:
            for word in patterns:
                content = content.replace(word, '')

        return content

    def get_first_post(search_num):
        """parse the first post of search"""

        cont, forum_unavailable = parse_search(search_num)
        not_found = True if cont and re.search(r'Запрошенной темы не существует', cont) else False

        if forum_unavailable or not_found:
            hash_num = None
            return hash_num, cont, forum_unavailable, not_found, None

        # FIXME – deactivated on Feb 6 2023 because seems it's not correct that this script should check status
        # FIXME – activated on Feb 7 2023 –af far as there were 2 searches w/o status updated
        get_status_from_content_and_send_to_topic_management(search_num, cont)
        topic_visibility = define_topic_visibility_by_content(cont)

        cont = prettify_content(cont)

        # craft a hash for this content
        hash_num = hashlib.md5(cont.encode()).hexdigest()

        return hash_num, cont, forum_unavailable, not_found, topic_visibility

    def update_first_posts_in_sql(searches_list):
        """generate a list of topic_ids with updated first posts and record in it PSQL"""

        num_of_searches_counter = 0
        num_of_site_errors_counter = 0
        list_of_searches_with_updated_f_posts = []
        pool = sql_connect()
        conn = pool.connect()
        try:
            for line in searches_list:
                num_of_searches_counter += 1
                topic_id = line.topic_id
                act_hash, act_content, site_unavailable, topic_not_found, topic_visibility = get_first_post(topic_id)

                if not site_unavailable and not topic_not_found:
                    # check the latest hash
                    stmt = sqlalchemy.text("""
                            SELECT content_hash, num_of_checks, content from search_first_posts WHERE search_id=:a
                            AND actual = TRUE;
                            """)
                    raw_data = conn.execute(stmt, a=topic_id).fetchone()

                    # if record for this search – exists
                    if raw_data:
                        last_hash = raw_data[0]

                        # if record for this search – outdated
                        if act_hash != last_hash and topic_visibility == 'regular':
                            # set all prev records as Actual = False
                            stmt = sqlalchemy.text("""
                                    UPDATE search_first_posts SET actual = FALSE WHERE search_id = :a;
                                    """)
                            conn.execute(stmt, a=topic_id)

                            # add new record
                            stmt = sqlalchemy.text("""
                                    INSERT INTO search_first_posts
                                    (search_id, timestamp, actual, content_hash, content, num_of_checks)
                                    VALUES (:a, :b, TRUE, :c, :d, :e);
                                    """)
                            conn.execute(stmt, a=topic_id, b=datetime.datetime.now(), c=act_hash, d=act_content, e=1)

                            list_of_searches_with_updated_f_posts.append(topic_id)

                    # if record for this search – does not exist – add a new record
                    else:
                        stmt = sqlalchemy.text("""INSERT INTO search_first_posts
                                                  (search_id, timestamp, actual, content_hash, content, num_of_checks)
                                                  VALUES (:a, :b, TRUE, :c, :d, :e);""")
                        conn.execute(stmt, a=topic_id, b=datetime.datetime.now(), c=act_hash, d=act_content, e=1)

                elif site_unavailable:
                    num_of_site_errors_counter += 1
                    logging.info(f'forum unavailable for search {topic_id}')
                    if num_of_site_errors_counter > 3:
                        notify_admin(f'LA FORUM UNAVAILABLE, che_posts tried {num_of_site_errors_counter} times.')
                        break

                elif topic_not_found:
                    update_one_topic_visibility(topic_id)

        except Exception as e:
            logging.info('exception in update_first_posts_and_statuses')
            logging.exception(e)

        conn.close()
        pool.dispose()

        logging.info(f'first posts checked for {num_of_searches_counter} searches')

        return list_of_searches_with_updated_f_posts

    global bad_gateway_counter
    global requests_session

    list_of_searches = get_list_of_topics()
    groups_list_all = generate_list_of_topic_groups()
    groups_list_now = define_which_topic_groups_to_be_checked(groups_list_all)
    groups_list_now = enrich_groups_with_topics(groups_list_now, list_of_searches)
    topics_list_now = [line for group in groups_list_now for line in group.s]

    if not topics_list_now:
        return None

    list_of_topics_with_updated_first_posts = update_first_posts_in_sql(topics_list_now)

    if not list_of_topics_with_updated_first_posts:
        return None

    publish_to_pubsub('topic_for_first_post_processing', list_of_topics_with_updated_first_posts)

    return None


def main(event, context):  # noqa
    """main function"""

    # to avoid function invocation except when it was initiated by scheduler (and pub/sub message was not doubled)
    if datetime.datetime.now().second > 5:
        return None

    global bad_gateway_counter
    bad_gateway_counter = 0

    # BLOCK 1. for checking if the first posts were changed
    update_first_posts_and_statuses()

    # BLOCK 2. small bonus: check one of topics, which has visibility='hidden' to check if it was not unhidden later.
    # It is done in this script only because there's no better place. Ant these are circa 40 hidden topics at all.
    update_visibility_for_one_hidden_topic()

    if bad_gateway_counter > 3:
        publish_to_pubsub('topic_notify_admin', f'[che_posts]: Bad Gateway {bad_gateway_counter} times')

    # Close the open session
    requests_session.close()

    return None

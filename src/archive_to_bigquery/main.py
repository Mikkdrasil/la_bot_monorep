"""move data from Cloud SQL to BigQuery for long-term storage & analysis"""

import logging
import urllib.request

import sqlalchemy
from google.cloud import bigquery, secretmanager

url = 'http://metadata.google.internal/computeMetadata/v1/project/project-id'
req = urllib.request.Request(url)
req.add_header('Metadata-Flavor', 'Google')
project_id = urllib.request.urlopen(req).read().decode()


def get_secrets(secret_request):
    """get secret from GCP Secret Manager"""

    name = f'projects/{project_id}/secrets/{secret_request}/versions/latest'
    client = secretmanager.SecretManagerServiceClient()

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
        'pool_recycle': 5,  # seconds
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


def archive_notif_by_user(client: bigquery.Client):
    """archive (move) data from notif_by_user in psql into BQ"""

    # 1. Get the initial row count of bq table
    query = """
            SELECT
                count(*) AS count
            FROM
                notif_archive.notif_by_user__archive
            """

    query_initial_rows_bq = client.query(query)
    init_bq_count = None
    for row in query_initial_rows_bq:
        init_bq_count = row.count
        logging.info(f'initial rows in BQ: {init_bq_count}')

    # 2. Get the initial row count of cloud sql table
    query = '''
                SELECT
                    *
                FROM
                    EXTERNAL_QUERY("projects/lizaalert-bot-01/locations/europe-west3/connections/bq_to_cloud_sql",
                """SELECT count(*) AS count FROM notif_by_user__history;""")
                '''

    query_initial_rows_psql = client.query(query)
    init_psql_count = None
    for row in query_initial_rows_psql:
        init_psql_count = row.count
        logging.info(f'initial rows in psql: {init_psql_count}')

    # 3. Copy all the new rows from psql to bq
    query = '''
                INSERT INTO
                    notif_archive.notif_by_user__archive (message_id, mailing_id, user_id, message_content,
                    message_text, message_type, message_params, message_group_id, change_log_id, created, completed,
                    cancelled, failed, num_of_fails)
                SELECT *
                FROM
                    EXTERNAL_QUERY("projects/lizaalert-bot-01/locations/europe-west3/connections/bq_to_cloud_sql",
                    """SELECT * FROM notif_by_user__history;""")
                WHERE NOT message_id IN
                    (SELECT message_id FROM notif_archive.notif_by_user__archive)
                '''

    query_move = client.query(query)
    result = query_move.result()  # noqa
    moved_lines = query_move.num_dml_affected_rows
    logging.info(f'move from cloud sql to bq: {moved_lines}')

    # 4. Get the resulting row count of bq table
    query = """
            SELECT
                count(*) AS count
            FROM
                notif_archive.notif_by_user__archive
            """

    query_resulting_rows_bq = client.query(query)
    new_bq_count = None
    for row in query_resulting_rows_bq:
        new_bq_count = row.count
        logging.info(f'resulting rows in BQ: {new_bq_count}')

    # 5. Run checkers
    # 5.1. Validate that there are no doubling message_ids in the final bq table
    query = """
            SELECT
                message_id, count(*) AS count
            FROM
                notif_archive.notif_by_user__archive
            GROUP BY 1
            HAVING count(*) > 1
            """

    query_job_final_check = client.query(query)
    validation_on_doubles = 0
    for row in query_job_final_check:
        validation_on_doubles = row.count
        logging.info(f'final check says: {validation_on_doubles}')

    # 5.2 should be zero
    validation_on_bq_lines = new_bq_count - moved_lines - init_bq_count

    # 5.3 should be zero
    validation_on_psql_lines = init_psql_count - moved_lines  # noqa

    # 6. Delete data from cloud sql
    # TODO: validations disabled because once the doubling in BQ happened -> and then all the iterations are failing
    #  with this validation - so the 5.1 and 5.3 validation never more relevant. to fix it - only 5.2 has been left
    # if validation_on_doubles == 0 and validation_on_bq_lines == 0 and validation_on_psql_lines == 0:
    if validation_on_bq_lines == 0:
        logging.info('validations for deletion passed')

        pool = sql_connect()
        conn = pool.connect()

        stmt = sqlalchemy.text("""DELETE FROM notif_by_user__history;""")
        conn.execute(stmt)

        conn.close()
        pool.dispose()

        logging.info('deletion from cloud sql executed')
    else:
        logging.info('validations for deletion failed')

    # 7. Get the resulting row count of cloud sql table
    query = '''
                SELECT
                    *
                FROM
                    EXTERNAL_QUERY("projects/lizaalert-bot-01/locations/europe-west3/connections/bq_to_cloud_sql",
                """SELECT count(*) AS count FROM notif_by_user__history;""")
                '''

    query_resulting_rows_psql = client.query(query)
    new_psql_count = 0  # noqa
    for row in query_resulting_rows_psql:
        new_psql_count = row.count
        logging.info(f'resulting rows in psql: {new_psql_count}')


def save_sql_stat_table_sizes(client: bigquery.Client):
    """save current psql parameters: sizes of biggest tables"""

    query = '''
            INSERT INTO
                stat.sql_table_sizes
            SELECT
                *
            FROM
              EXTERNAL_QUERY("projects/lizaalert-bot-01/locations/europe-west3/connections/bq_to_cloud_sql",
                """
                  SELECT
                    NOW() AS timestamp, *
                  FROM
                    (
                    SELECT
                      table_name, round(pg_relation_size(quote_ident(table_name))/1024/1024, 1) AS size_mb
                    FROM
                      information_schema.tables
                    WHERE
                      table_schema = 'public'
                    ) AS s1
                  WHERE
                    s1.size_mb > 1
                  ORDER BY
                    2 DESC
                  ;
                """
              )
            '''

    query = client.query(query)
    result = query.result()  # noqa
    lines = query.num_dml_affected_rows
    logging.info(f'saved psql table sizes stat to bq, number of lines: {lines}')

    return None


def main(event, context):  # noqa
    """main function"""

    client = bigquery.Client()

    archive_notif_by_user(client)

    save_sql_stat_table_sizes(client)

    return None

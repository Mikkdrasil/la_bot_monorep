from pathlib import Path

import psycopg2

from tests.common import get_config


def recreate_db_schema(script: str):
    config = get_config()

    connection = psycopg2.connect(
        dbname=config.cloud_postgres_db_name,
        user=config.cloud_postgres_username,
        password=config.cloud_postgres_password,
        port=config.pg_port,
        host=config.pg_host,
    )

    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute(script)
    pass
    connection.close()


def main():
    config = get_config()
    script = Path('tests/tools/db.sql').read_text()
    script = script.replace('<<CLOUD_POSTGRES_USERNAME>>', config.cloud_postgres_username)
    recreate_db_schema(script)
    print('test database recreated')


if __name__ == '__main__':
    main()

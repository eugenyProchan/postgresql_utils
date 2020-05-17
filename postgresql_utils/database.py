import psycopg2
from psycopg2.extras import execute_values
from psycopg2 import OperationalError, DatabaseError
from typing import Optional, Union
import logging


logger = logging.getLogger(__name__)


class DataBasePostgres:

    mapping_types = {'int4': 'integer',
                     'int8': 'integer',
                     '_int4': 'integer',
                     '_int8': 'integer'}

    def __init__(self, dns: str, autocommit: Optional[bool] = False):
        self.autocommit = autocommit
        self._dns = dns
        self._column_type = self._get_column_type()

    def execute(self,
                query: str,
                cursor_factory: Optional = None)-> Union[dict, list, tuple, None]:
        with self._executed_cursor(query, cursor_factory) as cursor:
            message_from_db = cursor.statusmessage
            if message_from_db in ['CREATE TABLE',
                                   'TRUNCATE TABLE',
                                   'DELETE TABLE',
                                   'REFRESH MATERIALIZED VIEW']:
                return None
            return cursor.fetchall()

    def copy_to_db(self, query: str,
                        target_db: 'DataBasePostgres',
                        target_table_name: str,
                        chank_size:Optional[int] = 2000) -> None:

        with self._executed_cursor(query: str) as source_cursor, target_db._get_cursor() as target_cursor:
            create_sql = self._generate_create_table_sql_from_cursor(source_cursor, target_table_name)
            insert_sql = self._generate_insert_table_sql_from_cursor(source_cursor, target_table_name)

            target_db.execute(create_sql)
            target_db.execute(f'truncate table {target_table_name}')

            try:
                while True:
                    records = source_cursor.fetchmany(chank_size)
                    if not records:
                        break
                    execute_values(target_cursor,
                                    insert_sql,
                                    records)
                target_cursor.connection.commit()
                logger.info(f'Data have been transfered in {target_table_name}')

            except DatabaseError as exc:
                raise exc('Exception in copy_to_db method ' + query)

    def _get_cursor(self, cursor_factory:Optional=None) -> psycopg2.extensions.cursor:
        try:
            with psycopg2.connect(**self._dns) as conn:
                conn.autocommit = self.autocommit
                return conn.cursor(cursor_factory=cursor_factory)
        except OperationalError as exc:
            self.logger.exception(self._dns, exc_info=True)
            raise exc

    def _executed_cursor(self, query: str, cursor_factory: Optional=None) -> psycopg2.extensions.cursor:
        cursor = self._get_cursor(cursor_factory=cursor_factory)
        try:
            cursor.execute(query)
            logger.info(cursor.query)
        except DatabaseError as exc:
            raise exc
        return cursor

    def _get_column_type(self) -> dict:
        with self._executed_cursor('select oid, typname from pg_type') as cursor:
            return {code: column_type for code, column_type in cursor.fetchall()}

    def _get_dict_types(self, cursor: psycopg2.extensions.cursor) -> dict:
        return {column.name: DataBasePostgres.mapping_types.get(self._column_type[column.type_code],
                self._column_type[column.type_code])
                for column in cursor.description}

    def _generate_create_table_sql_from_cursor(self,
                                               source_cursor: psycopg2.extensions.cursor,
                                               target_table: str) -> str:
        create_sql = f'create table if not exists {target_table}'
        for name, column_type in self._get_dict_types(source_cursor).items():
            if column_type == 'varchar':
                column_type = 'varchar(1000)'
            create_sql += f'{name} {column_type} ,'
        create_sql = create_sql[:-1] + ')'
        return create_sql

    def _generate_create_sql_from_cursor(cursor: psycopg2.extensions.cursor):
        create_sql = f'create table if not exists {target_table}'
        for name, column_type in self._get_dict_types(source_cursor).items():
            if column_type == 'varchar':
                column_type = 'varchar(1000)'
            create_sql += f'{name} {column_type} ,'
        create_sql = create_sql[:-1] + ')'

    def _generate_insert_table_sql_from_cursor(self,
                                               source_cursor: psycopg2.extensions.cursor,
                                               target_table: str) -> str:
        columns_name = ','.join(column.name for column in source_cursor.description)
        return f'INSERT INTO {target_table} ({columns_name}) VALUES %s'

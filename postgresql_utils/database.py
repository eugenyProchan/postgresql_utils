import psycopg2
from psycopg2.extras import execute_values
from psycopg2 import OperationalError, DatabaseError
from psycopg2.extras import Json
from psycopg2.extensions import register_adapter
from typing import Optional, Union
import logging


class DataBasePostgres:

    mapping_types = {'int4': 'integer',
                     'int8': 'integer',
                     '_int4': 'integer',
                     '_int8': 'integer'}

    def __init__(self, dsn_dict):
        self._dsn_dict = dsn_dict
        self._column_type = self._get_column_type()
        self.logger = logging.getLogger('DataBasePostgres')


    def _get_cursor(self, cursor_factory: Optional = None) -> psycopg2.extensions.cursor:
        try:
            with psycopg2.connect(**self._dsn_dict) as conn:
                return conn.cursor(cursor_factory=cursor_factory)
        except OperationalError as exc:
            raise exc

    def _executed_cursor(self, query, cursor_factory:Optional=None) -> psycopg2.extensions.cursor:
        cursor = self._get_cursor(cursor_factory=cursor_factory)
        try:
            self.logger.info(cursor.query)
            cursor.execute(query)
        except DatabaseError as exc:
            raise exc
        return cursor

    def _get_column_type(self) -> dict:
        with self._executed_cursor('select oid, typname from pg_type') as cursor:
            return {code: column_type for code, column_type in cursor.fetchall()}

    def _get_dict_types(self, cursor: psycopg2.extensions.cursor) -> dict:
        return {column.name: DataBasePostgres.mapping_types.get(
                self._column_type[column.type_code],
                self._column_type[column.type_code])
                for column in cursor.description}

    def execute(self, query:str, cursor_factory:Optional = None) -> Union[dict, list, tuple, None]:
        with self._executed_cursor(query, cursor_factory) as cursor:
            if cursor.statusmessage in ['CREATE TABLE',
                                        'TRUNCATE TABLE',
                                        'DELETE TABLE',
                                        'REFRESH MATERIALIZED VIEW']:
                return None
            return cursor.fetchall()

    def _generate_create_table_sql_from_cursor(self, source_cursor: psycopg2.extensions.cursor,
                                                     target_table: str) -> str:
        create_sql = 'create table if not exists {} ('.format(target_table)
        for name, column_type in self._get_dict_types(source_cursor).items():
            if column_type == 'varchar':
                column_type = 'varchar(1000)'
            create_sql += '"{}" {} ,'.format(name, column_type)
        create_sql = create_sql[:-1] + ')'
        return create_sql

    def _generate_insert_table_sql_from_cursor(self, source_cursor: psycopg2.extensions.cursor, 
                                                     target_table: str) -> str:
        columns_name = ','.join('"{0}"'.format(column.name) for column in source_cursor.description)
        return 'INSERT INTO {} ({}) VALUES %s'.format(target_table, columns_name)

    def copy_to_db(self,
                   query: str,
                   target_db: 'DataBasePostgres',
                   target_table_name: str,
                   chank_size: Optional[int] = 2000) -> None:

        with self._executed_cursor(query) as source_cursor, target_db._get_cursor() as target_cursor:
            create_sql = self._generate_create_table_sql_from_cursor(source_cursor, target_table_name)
            insert_sql = self._generate_insert_table_sql_from_cursor(source_cursor, target_table_name)
            types = [type_name for type_name in self._get_dict_types(source_cursor).values()]

            target_db.execute(create_sql)
            target_db.execute(f'truncate table {target_table_name}')

            try:
                while True:
                    raw_records = source_cursor.fetchmany(chank_size)

                    records = list(
                            map(
                                lambda record: tuple(Json(value) if type_name == 'json' else value for value, type_name in zip(record, types)),
                                raw_records
                            )
                        )

                    if not records:
                        break
                    execute_values(target_cursor,
                                   insert_sql,
                                   records)
                target_cursor.connection.commit()
                self.logger.info(f'Data was transfered {insert_sql}')

            except DatabaseError as exc:
                self.logger.exception('Exception in copy_to_db method ' + query, exc_info=True)
                raise exc

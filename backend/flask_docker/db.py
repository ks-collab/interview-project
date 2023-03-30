import time
from datetime import datetime, timezone
from contextlib import contextmanager
import logging
from typing import (
    Any,
    Dict,
    Generator,
    Iterable,
    Tuple,
    Sequence,
    Optional,
    List,
    Union,
)

import pymysql
from pymysql import cursors

import sys

root = logging.getLogger()
root.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
root.addHandler(handler)


class Database:
    max_retries = 1  # maximum number of retries when a connection to the database cannot be established

    def __init__(self, database: str, autocommit: bool = True):
        """
        Args:
            database: name of database to connect to

            autocommit: if this is True, every sql query automatically
            commits. If False, sql queries are not committed until conn.commit()
            or db.commit() is called, or exiting the context manager without
            an exception raised, or until the destructor is called. Exception:
            the function execute_sql() ignores this and always commits its sql
            arguments. When autocommit is False and Database is used as
            a context manager (with Database(autocommit=False) as db:),
            conn.rollback() is called when an exception is raised.
        """
        self.database = database
        self.autocommit: bool = autocommit
        self.conn: pymysql.connections.Connection = self._get_connection()

    def __del__(self):
        # Destructor: ensure database changes are committed even for self.autocommit = False
        if self.conn.open:
            self.conn.commit()
            self.conn.close()

    def _get_connection(self) -> pymysql.connections.Connection:
        """Creates a connection to the database

        Returns
        -------
        pymysql.connections.Connection

        Raises
        ------
        RuntimeError
            Failed to connect to database after Database.max_retries
        """
        kwargs = {
            "host": "mariadb",
            "port": 3306,
            "user": "root",
            "password": "password",
            "db": self.database,
            "use_unicode": True,
            "charset": "utf8mb4",
            "cursorclass": cursors.DictCursor,
            "autocommit": self.autocommit,
        }
        for retry in range(Database.max_retries):
            try:
                conn = pymysql.connect(**kwargs)
                return conn
            except:
                logging.info(
                    "Trying to connect to database (%s)",
                    f"{retry}/{Database.max_retries}",
                )
                if retry < Database.max_retries - 1:
                    time.sleep(2**retry)
        raise RuntimeError(
            f"Failed to connect to database after {Database.max_retries} retries"
        )

    def __enter__(self):
        return self

    def __exit__(self, exception, value, tb):
        # for context manager, db changes are rolled back on error if
        # self.autocommit is False; otherwise, if self.autocommit is True, every
        # statement has already committed and cannot be rolled back
        if exception is not None:
            self.conn.rollback()
        else:
            self.conn.commit()

    @contextmanager
    def cursor(self, *args, **kwargs) -> Generator[cursors.DictCursor, None, None]:
        """Context manager for database cursors that autocommit changes and close the cursor when exiting the context

        Yields
        -------
        pymysql.cursors.DictCursor
        """
        self.conn.ping(reconnect=True)
        cursor = self.conn.cursor()
        try:
            yield cursor
        finally:
            if self.autocommit:
                # this may not actually be necessary since each individual query would've already committed
                self.conn.commit()
            cursor.close()

    def _log_query(self, sql: str, args: Iterable):
        """Logs sql queries and their arguments using the logging module

        Parameters
        ----------
        sql : str
        args : Tuple
        """
        argstr = []
        for arg in args:
            s = f"{arg}"
            argstr.append((s[:16] + "...") if len(s) > 16000 else s)
        argstr = ", ".join(map(lambda arg: f'"{arg}"', argstr))
        logging.debug("sql  = %s\n          args = (%s)", sql, argstr)

    def fmt_datetime(self, dt: datetime) -> str:
        """Converts python datetime objects to datestrings that MySQL understands

        Parameters
        ----------
        dt : datetime

        Returns
        -------
        str
            String in "%Y-%m-%d %H:%M:%S.%f" format
        """
        return dt.strftime(r"%Y-%m-%d %H:%M:%S.%f")

    def utcnow(self) -> str:
        """Get SQL datestring for the current time in UTC

        Returns
        -------
        str
            UTC current time in "%Y-%m-%d %H:%M:%S.%f" format
        """
        return self.fmt_datetime(datetime.now(timezone.utc))

    def insert(self, table: str, obj: Dict) -> int:
        """Inserts a dict-like object into a table

        Parameters
        ----------
        table : str
            name of the database table
        obj : Dict
            keys are columns

        Returns
        -------
        int
            lastrowid
        """
        keys = [k for k in obj.keys() if k != "id"]
        vals = ",".join(["%s" for _ in keys])
        cols = ",".join(map(lambda key: f"`{key}`", keys))
        sql = f"INSERT INTO {table} ({cols}) VALUES ({vals})"
        args = [obj[k] for k in keys]
        for i, arg in enumerate(args):
            if isinstance(arg, datetime):
                args[i] = self.fmt_datetime(arg)
        lastrowid: Optional[int] = None
        with self.cursor() as cursor:
            cursor.execute(sql, tuple(args))
            lastrowid = cursor.lastrowid
        if not isinstance(lastrowid, int):
            raise Exception("Database::insert failed")

        return lastrowid

    def update(
        self,
        table: str,
        obj: Dict,
        where: Optional[Tuple[str, Optional[Any]]] = None,
        where_list: Optional[List[Tuple[str, Union[int, str]]]] = None,
    ) -> None:
        """Applies updates from dict-like object.
            Example usage: `update(table='people', obj={'name': 'bar'}, where=('id', 5))`

        Parameters
        ----------
        table : str
        obj : Dict
        where : Tuple[str, int]
            Where column = value
        """

        keys = [k for k in obj.keys() if k != "id"]
        updates = ",".join([f"`{key}`=%s" for key in keys])

        if where is not None:
            sql = f"UPDATE {table} SET {updates} WHERE `{where[0]}`=%s"
            args = [obj[k] for k in keys] + [where[1]]
        elif where_list is not None:
            where_cols, where_args = zip(*where_list)
            where_cols = " AND ".join(
                [f"{where_col}=%s" for where_col in where_cols])
            sql = f"UPDATE {table} SET {updates} WHERE {where_cols}"
            args = [obj[k] for k in keys] + list(where_args)
        else:
            raise ValueError("Need some column/values to index on")
        for arg in args:
            if isinstance(arg, datetime):
                arg = self.fmt_datetime(arg)
        self._log_query(sql, args)
        with self.cursor() as cursor:
            cursor.execute(sql, tuple(args))

    def insert_on_dup_update(self, table: str, obj: Dict) -> int:
        keys = [k for k in obj.keys() if k != "id"]
        update_keys = [k for k in keys if k != "created_at"]
        cols = ", ".join(map(lambda key: f"`{key}`", keys))
        vals = ", ".join(["%s" for _ in keys])
        updates = ", ".join(
            map(lambda key: f"{key} = VALUES({key})", update_keys))
        sql = f"INSERT INTO {table} ({cols}) VALUES ({vals}) ON DUPLICATE KEY UPDATE {updates}"
        args = [obj[k] for k in keys]
        for arg in args:
            if isinstance(arg, datetime):
                arg = self.fmt_datetime(arg)

        self._log_query(sql, args)

        lastrowid: Optional[int] = None
        with self.cursor() as cursor:
            cursor.execute(sql, tuple(args))
            lastrowid = cursor.lastrowid
        if not isinstance(lastrowid, int):
            raise Exception("Database::insert_on_dup_update failed")

        return lastrowid

    def fetch(self, sql: str, args: Tuple = ()) -> Sequence[Dict]:
        """Runs a SELECT sql query and returns a list of dictionaries

        Parameters
        ----------
        sql : str
            SELECT query
        args : Tuple, optional
            query args, by default ()

        Returns
        -------
        Sequence[Dict]
            List of rows
        """
        self._log_query(sql, args)
        with self.cursor() as cursor:
            cursor.execute(sql, args)
            rows = list(cursor.fetchall())
            return rows

    def execute(self, sql: str, args: Tuple = ()) -> int:
        """Executes a sql statement

        Parameters
        ----------
        sql : str

        args : Tuple, optional
            by default ()

        Returns
        -------
        int
            number of rows affected
        """
        self._log_query(sql, args)
        with self.cursor() as cursor:
            num_affected = cursor.execute(sql, tuple(args))
            return num_affected

    def execute_many(self, lines: Sequence[str]) -> None:
        """Execute a sequence of sql queries, usually lines from a .sql file

        Parameters
        ----------
        lines : Sequence[str]
            lines from a .sql file, e.g. using readlines()
        """
        stmts = []
        DELIMITER = ";"
        stmt = ""
        with self.cursor() as cursor:
            for line in lines:
                if not line.strip():
                    continue
                if line.startswith("--"):
                    continue
                if "DELIMITER" in line:
                    DELIMITER = line.split()[1]
                    continue
                if DELIMITER not in line:
                    stmt += line.replace(DELIMITER, ";")
                    continue
                if stmt:
                    stmt += line
                    stmts.append(stmt.strip())
                    stmt = ""
                else:
                    stmts.append(line.strip())
            for stmt in stmts:
                cursor.execute(stmt)
            self.conn.commit()

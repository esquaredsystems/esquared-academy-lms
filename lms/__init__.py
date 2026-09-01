"""
Database driver shim.

Django talks to MySQL through the `MySQLdb` module name. The reference
driver, mysqlclient, provides it but compiles against the MySQL client
library, which needs Homebrew's mysql-client and pkg-config on macOS.
PyMySQL is a pure-Python implementation of the same interface and needs no
build step, so it is what requirements.txt pins.

If mysqlclient is installed it wins — this shim only fills the gap.
"""

try:  # pragma: no cover - import-time branch
    import MySQLdb  # noqa: F401
except ImportError:  # pragma: no cover
    try:
        import pymysql

        pymysql.install_as_MySQLdb()
    except ImportError:
        # Neither driver present: fine for the SQLite test database, and
        # Django raises a clear error if MySQL is actually needed.
        pass

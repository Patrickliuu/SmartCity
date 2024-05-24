# Utilities to access the UWO data set.
# Usage:
#   1. Select a method to connect to the database below.
#   2. Set the correct path to the sqlite file or set the connection parameters for MariaDB.
#
# Done by KPP(pern) in 2024!

import os
import pendulum
import pathlib
from dotenv import find_dotenv, load_dotenv

import contextlib
import sqlite3
import sqlalchemy
import traceback

import pandas as pd
from typing import Optional


###############
# DEFINITIONS #
###############

# select the DB connection type
# 0 = sqlite3
# 1 = MariaDB (to use MariaDB, enclose the table name "signal" in backticks)
# 2 = PostgreSQL
DBType = 0

# define paths to local sqlite3 DB
DBSourceDirectory = "/home/pindalu/FS2024/DSIOT/smartcity-01-Patrickliuu/data"
#DBFileName = "data_UWO_2019-01_2020-01.sqlite"
#DBFileName = "data_UWO_2020-01_2021-01.sqlite"
#DBFileName = "data_UWO_2021-01_2022-01.sqlite"
DBFileName = "data_uwo_2019-01_2022-01.sqlite"

DBContentList = "C:/UWO dataset/A_field_observations/slice_information.csv" # Do we need a content list?


# construct paths
db = pathlib.Path(DBSourceDirectory) / DBFileName
cl = pathlib.Path(DBSourceDirectory) / DBContentList


### Misc

# load .env file
load_dotenv(find_dotenv())



##### DB connectors

@contextlib.contextmanager
def _open_sqlite(db_file):
    """ Connector to the sqlite3 database. """
    
    conn = sqlite3.connect(db_file)
    try:
        yield conn
    except BaseException as e:
        print(f"An error occurred: {e}")
        traceback.print_exc()
        conn.rollback()
        raise
    finally:
        conn.close()
        


@contextlib.contextmanager
def _open_mariadb():
    """ Connector to the MariaDB database. """

    # get connection parameters from .env
    DBUser = os.environ.get('Mariadb.User')
    DBPW = os.environ.get('Mariadb.PW')
    DBHost = os.environ.get('Mariadb.Host')
    DBPort = os.environ.get('Mariadb.Port')
    DBName = os.environ.get('Mariadb.DBName')
          
    # pandas somehow only supports sqlalchemy and not pymysql and not mysql.connector
    # https://docs.sqlalchemy.org/en/20/dialects/mysql.html#module-sqlalchemy.dialects.mysql.mariadbconnector
    engine = sqlalchemy.create_engine(f"mariadb+mariadbconnector://{DBUser}:{DBPW}@{DBHost}:{DBPort}/{DBName}")
    
    try:
        conn = engine.connect()
        yield conn
    except BaseException as e:
        print(f"An error occurred: {e}")
        traceback.print_exc()
        raise
    finally:
        conn.close()





@contextlib.contextmanager
def _open_postgresdb():
    """Connector to the PostgreSQL database."""

    # get connection parameters from .env
    DBUser = os.environ.get('PostgreSQL.User')
    DBPW = os.environ.get('PostgreSQL.PW')
    DBHost = os.environ.get('PostgreSQL.Host')
    DBPort = os.environ.get('PostgreSQL.Port')
    DBName = os.environ.get('PostgreSQL.DBName')

    # Format for PostgreSQL connection string using psycopg2
    # postgresql+psycopg2://<username>:<password>@<host>:<port>/<dbname>
    engine = sqlalchemy.create_engine(f"postgresql+psycopg2://{DBUser}:{DBPW}@{DBHost}:{DBPort}/{DBName}")

    try:
        conn = engine.connect()
        yield conn
    except BaseException as e:
        print(f"An error occurred: {e}")
        traceback.print_exc()
        raise
    finally:
        conn.close()


##### DB queries

def query(sql_query: str) -> pd.DataFrame:
    """ Query the UWO database and return a dataframe. Mostly for internal use. """

    if DBType == 0:
        with _open_sqlite(db) as conn:
            return pd.read_sql_query(sql_query, conn)
    elif DBType == 1:
        with _open_mariadb() as conn:
            return pd.read_sql_query(sql_query, conn)
    elif DBType == 2:
        with _open_postgresdb() as conn:
            return pd.read_sql_query(sql_query, conn) 
    else:
        raise NotImplementedError("The specified DBtype is not supported")
    

def GetAllVariables() -> pd.DataFrame:
    """ Lists all variables in the UWO database, i.e. the list of 'what has been measured'. """
    
    sql = f"""
    SELECT
        name,
        unit,
        description
    FROM variable;
    """
    
    return query(sql)


def GetSitesWithVariable(variable: str) -> pd.DataFrame:
    """ Queries all sites that have recorded a specific variable. 
    
        Note: The table name signal is a reserved word in MariaDB and, thus, needs to
        be enclosed in backticks, while for PostgreSQL and sqlite, no quotes are needed.
    """

    # ogiginal version (keep for reference)
    # sql = f"""
    # WITH variable_ids as (SELECT variable_id 
    #                       FROM variable 
    #                       WHERE variable.name = '{variable}'), 
    #      site_ids as (SELECT DISTINCT site_id 
    #                   FROM `signal`
    #                   WHERE signal.variable_id IN (SELECT variable_id 
    #                                                FROM variable_ids))
    # SELECT name, site_id
    # FROM site
    # WHERE site_id IN (SELECT site_id 
    #                   FROM site_ids);
    # """

    # improved version from chatGPT
    sql = f"""
    SELECT s.name, sig.site_id
    FROM site s
    JOIN (
        SELECT DISTINCT sig.site_id
        FROM signal sig
        JOIN variable v ON sig.variable_id = v.variable_id
        WHERE v.name = '{variable}'
    ) AS sig ON s.site_id = sig.site_id;
    """
        
    return query(sql)


def GetSensorsForSite(site: str) -> pd.DataFrame:
    """ Queries all sensors of a specific site. """
    
    sql = f"""
    WITH source_ids as (SELECT DISTINCT source_id 
                        FROM signal
                        WHERE signal.site_id IN (SELECT site_id 
                                                 FROM site
                                                 WHERE site.name = '{site}'))
    SELECT source_id, name, description
    FROM source
    WHERE source.source_id IN (SELECT source_id
                               FROM source_ids);
    """
    
    return query(sql)



def GetTimeSeries(source_name: str, start_date: Optional[str]=None, end_date: Optional[str]=None, limit: Optional[int]=None) -> pd.DataFrame:
    """ Queries the time series of the given sensor.  
    
        Note: The table name signal is a reserved word in MariaDB and, thus, needs to
        be enclosed in backticks!
    """
    
    # Remark: WITH clause produces a Common Table Expression, which cannot be used in WHERE; it 
    # is more like a table than a variable. Just use the subquery directly in the WHERE clause.
    # Or use variables, not sure this works in MariaDB and sqlite3.
    # SET @siteId = (SELECT site_id FROM site WHERE site.name = 'rub128basin_usterstr');
    # WHERE signal.site_id = @siteId
    # Remark: user-defined session varialbes are not supported in sqlite3
    
    sql = f"""
    SELECT timestamp,
           value
    FROM signal
    WHERE signal.source_id IN (SELECT source_id
                               FROM source
                               WHERE name = '{source_name}')
    """
    
    if start_date is not None:
      sql += f"""AND signal.timestamp >= '{start_date}'
      """
      
    if end_date is not None:
        sql += f"""AND signal.timestamp <= '{end_date}'
        """
    
    sql += f"""ORDER BY signal.timestamp
    """
    
    if limit is not None:
        sql += f"LIMIT {limit};"
    else: sql += ";"

    q=query(sql)
    
    # convert timestamp to datetime
    q['timestamp'] = pd.to_datetime(q['timestamp'], errors='coerce')
    
    return q
    

def GetMetaData(source_name: str, start_date: Optional[str]=None, end_date: Optional[str]=None, limit: Optional[int] = None) -> pd.DataFrame:
    """Queries the database for the meta data of the given sensor."""

    sql = f"""
    SELECT timestamp_start,
           timestamp_end,
           comment,
           additional_meta_info
    FROM `meta_data_history`
    WHERE meta_data_id = (SELECT meta_data_id
                          FROM `meta_data`
                          WHERE source_id = (SELECT source_id
                                             FROM `source`
                                             WHERE name = '{source_name}'))
    """
    
    if start_date is not None:
      sql += f"""AND timestamp_start >= '{start_date}'
      """
      
    if end_date is not None:
        sql += f"""AND timestamp_start <= '{end_date}'
        """
    
    sql += f"""ORDER BY timestamp_start
    """
    
    if limit is not None:
        sql += f"LIMIT {limit};"
    else: sql += ";"

    q=query(sql)
    
    # convert timestamp to datetime
    q['timestamp_start'] = pd.to_datetime(q['timestamp_start'], errors='coerce')
    q['timestamp_end'] = pd.to_datetime(q['timestamp_end'], errors='coerce')
    q['comment'] = q['comment'].astype('string')
    q['sensor_name'] = source_name
    return q


def GetFlowRateTimeSeries() -> pd.DataFrame: # Never hardcode the variable name! source_name: str, {source_name}
    """Queries the time series of all flow_rate signals."""
    print("Starting")
    sql = """
    SELECT sig.signal_id,
           sig.timestamp,
           sig.value,
           src.name AS source_name,
           st.name AS site_name,
           var.name AS variable_name
    FROM signal sig
    JOIN source src ON sig.source_id = src.source_id
    JOIN site st ON sig.site_id = st.site_id
    JOIN variable var ON sig.variable_id = var.variable_id
    WHERE var.name = 'flow_rate'
    ORDER BY sig.timestamp;
    """

    return query(sql)


# executed when run as script (outside Jupyter)
if __name__ == "__main__":
    
    print("executing UWOtools as script...");
    tic = pendulum.now();

    # which conda environment is in use?
    import os
    conda_prefix = os.environ.get('CONDA_PREFIX', None)
    if conda_prefix:
        environment_name = os.path.basename(conda_prefix)
        print(f"Conda environment in use: {environment_name}")
    else:
        print("Not running in a Conda environment.")

    # === test GetAllVariables
    allVariables = GetAllVariables()
    print(allVariables.head())


    
    toc = pendulum.now() - tic
    print(f"Wall time: {toc.minutes:02}:{toc.seconds:02}+{toc.microseconds/1000:03}") # type: ignore
    
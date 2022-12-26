import psycopg2
from db_config.config import *
def create_table(symbol, opens, closes, order_id, profit, strategy, start_transacttime, end_transacttime):
    try:
        connection = psycopg2.connect(
            host=host,
            user=user,
            password=password,
            database=db_name
        )
        connection.autocommit = True

        with connection.cursor() as cursor:
            cursor.execute(
                f"""INSERT INTO traidings (symbol, opens, closes, order_id, profit, strategy, start_transacttime, end_transacttime) 
                VALUES ('{symbol}', {opens}, {closes}, '{order_id}', {profit}, '{strategy}', {start_transacttime}, {end_transacttime})
                ;"""
            )
    finally:
        if connection:
            connection.close()

from time import sleep
import vectorbt as vbt
import numpy as np
import talib

import requests                    # for "get" request to API
import json                        # parse json into a list
import pandas as pd                # working with data frames
import datetime as dt              # working with dates

from db_config.db_create_table import create_table

from binance.client import Client
from config.config import api_key, secret_key
client = Client(api_key, secret_key, {"verify": True, "timeout": None})


last_order = {
'SCRTUSDT': ['sell', 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],

}

while True:
    try:
        # UT Bot Parameters
        SENSITIVITY = 0.000800
        ATR_PERIOD = 1

        # Ticker and timeframe
        INTERVAL = "15m"

        # Backtest start/end date
        START = dt.datetime(2022,11,17)
        END   = dt.datetime.now()

        # Здесь описывается стратегия для добавления в базу
        strategy_db = '№ 3'

        # Get data from Binance
        def get_binance_bars(symbol, interval, startTime, endTime):
        
            url = "https://api.binance.com/api/v3/klines"

            startTime = str(int(startTime.timestamp() * 1000))
            endTime = str(int(endTime.timestamp() * 1000))
            limit = '1000'

            req_params = {"symbol" : symbol, 'interval' : interval, 'startTime' : startTime, 'endTime' : endTime, 'limit' : limit}

            df = pd.DataFrame(json.loads(requests.get(url, params = req_params).text))

            if (len(df.index) == 0):
                return None

            df = df.iloc[:, 0:6]
            df.columns = ['datetime', 'Open', 'High', 'Low', 'Close', 'Volume']

            df.Open      = df.Open.astype("float")
            df.High      = df.High.astype("float")
            df.Low       = df.Low.astype("float")
            df.Close     = df.Close.astype("float")
            df.Volume    = df.Volume.astype("float")

            df['adj_close'] = df['Close']

            df.index = [dt.datetime.fromtimestamp(x / 1000.0) for x in df.datetime]

            return df

        for key, values in last_order.items():
            def pd_datas(TICKER, INTERVAL, START, END):
                df_list = []
                while True:
                    new_df = get_binance_bars(TICKER, INTERVAL, START, END)
                    if new_df is None:
                        break
                    df_list.append(new_df)
                    START = max(new_df.index) + dt.timedelta(0, 1)
                return pd.concat(df_list)
        pd_data = pd_datas(key, INTERVAL, START, END)

        # Compute ATR And nLoss variable
        pd_data["xATR"] = talib.ATR(pd_data["High"], pd_data["Low"], pd_data["Close"], timeperiod=ATR_PERIOD)
        pd_data["nLoss"] = SENSITIVITY * pd_data["xATR"]

        #Drop all rows that have nan, X first depending on the ATR preiod for the moving average
        pd_data = pd_data.dropna()
        pd_data = pd_data.reset_index()

        # Function to compute ATRTrailingStop
        def xATRTrailingStop_func(close, prev_close, prev_atr, nloss):
            if close > prev_atr and prev_close > prev_atr:
                return max(prev_atr, close - nloss)
            elif close < prev_atr and prev_close < prev_atr:
                return min(prev_atr, close + nloss)
            elif close > prev_atr:
                return close - nloss
            else:
                return close + nloss

        # Filling ATRTrailingStop Variable
        pd_data["ATRTrailingStop"] = [0.0] + [np.nan for i in range(len(pd_data) - 1)]

        for i in range(1, len(pd_data)):
            pd_data.loc[i, "ATRTrailingStop"] = xATRTrailingStop_func(
                pd_data.loc[i, "Close"],
                pd_data.loc[i - 1, "Close"],
                pd_data.loc[i - 1, "ATRTrailingStop"],
                pd_data.loc[i, "nLoss"],
            )


        # Calculating signals
        ema = vbt.MA.run(pd_data["Close"], 1, short_name='EMA', ewm=True)

        pd_data["Above"] = ema.ma_crossed_above(pd_data["ATRTrailingStop"])
        pd_data["Below"] = ema.ma_crossed_below(pd_data["ATRTrailingStop"])

        pd_data["Buy"] = (pd_data["Close"] > pd_data["ATRTrailingStop"]) & (pd_data["Above"]==True)
        pd_data["Sell"] = (pd_data["Close"] < pd_data["ATRTrailingStop"]) & (pd_data["Below"]==True)


        # Run the strategy
        pf = vbt.Portfolio.from_signals(
            pd_data["Close"],
            entries=pd_data["Buy"],
            short_entries=pd_data["Sell"],
            upon_opposite_entry='ReverseReduce', 
            freq = "d"
        )
       
        balance = float(client.get_asset_balance(asset='USDT')['free'])
        buy_order = {}
        sell_order = {}
            

        if values[0] == "buy" and (pd_data.tail(1)['Sell'].value_counts().index[-1] == True):
            try:
                sel_order = client.order_market_sell(
                    symbol=key,
                    quantity=last_order[key][3])
                sell_order = sel_order
                print(sell_order)
            except:
                last_order[key][3] = int(last_order[key][3])
                continue
            last_order[key][10] = sel_order['transactTime']  # добавляет в словарь юникс время покупки в милесекундах
            last_order[key][8] = float(sell_order['cummulativeQuoteQty'])  #в словарь добавляем стоимость продажи
            values[2] = float(sell_order['fills'][0]['price']) # в словарь добавляет цену монеты
            print(f'Пора продавать криптовалюту: {key}')
            print(f'Ордер ID: {values[6]}')
            print(f'индикатор закрытия: {values[2]}')
            print(f'Ваш баланс на USDT: {balance}')
            proverka = values[8] - values[7]
            profit = proverka * 100 / values[7]
            print(f'Стоимость за сколько продали: {last_order[key][8]}$')
            print(f'Сколько получили прибыли: {last_order[key][8] - last_order[key][7]}')
            print(f'Ваш процент прибыли: {profit} %')
            print('──────────────────')
            
            create_table(key, values[1], values[2], values[6], profit, strategy_db, values[9], values[10])
            last_order[key][0] = "sell"

        # if float(balance) < 15:
        #     print(f'Ваш баланс недостаточен для открытие ордеров: {balance}\nВам не хватает: {25 - balance}USDT')
        #     sleep(50)
        #     continue

        if values[0] == "sell" and (pd_data.tail(1)['Buy'].value_counts().index[-1] == True): 
            # REPLACE COMMENT: Create a buy order using your exchange's API.
            order = client.order_market_buy(
                symbol=key,
                quoteOrderQty=17.5)
            buy_order = order
            print(buy_order)
            last_order[key][9] = buy_order['transactTime']  # добавляет в словарь юникс время покупки в милесекундах
            last_order[key][7] = float(buy_order['cummulativeQuoteQty'])  #в словарь добавляем сколько купили за доллары
            values[6] = buy_order['orderId']  # в словарь добавляем Order ID
            print(f'вы купили криптовалюту: {key}')
            print(f'Ордер ID: {values[6]}')
            last_order[key][3] = float(buy_order['origQty']) # в словарь добавляет количество монет
            last_order[key][4] = float(buy_order['fills'][0]['commission']) # в словарь добавляет коммисию
            last_order[key][1] = float(buy_order['fills'][0]['price']) # в словарь добавляет цену
            if last_order[key][4] > 0:
                proverka = last_order[key][3] - last_order[key][4] - last_order[key][4] # здесь количество монет 2 раза отнимает от суммы коммисии
                last_order[key][3] = proverka
                step_size = float(client.get_symbol_info(key)['filters'][2]['stepSize'])
                a = step_size  # общая длина шага (к примеру 45.444)
                c = str(a) # конвертируем шаг в стринг
                c.split('.') # разбиваем строку шаг по . и получаем список ['0', '005']
                dot_position = len(c.split('.')[1]) # получаем длину второго элемента списка шага '005'
                last_order[key][5] = dot_position # сохраняем длину шага в dict в значениях (индекс 5)
                print(f'Узнаем длину шага: {last_order[key][5]}')
                n = dot_position
                a = last_order[key][3]
                last_order[key][3] = int(a*10**n)/10**n
                if dot_position == 0:
                    last_order[key][3] = int(last_order[key][3])
            print(f'Индикатор открытия: {values[1]}') 
            print(f'Стоимость за сколько купли: {last_order[key][7]}$')
            print(f'Монеты доступные для продажи: {last_order[key][3]}')
            print(f'Ваш баланс на USDT: {balance}')
            print('──────────────────')
            last_order[key][0] = "buy"

    except Exception as e:
        print("Oops!", e, "occurred.")
        sleep(50)
        continue

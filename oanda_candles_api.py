import requests as http
import numpy as np
import pandas as pd
import arrow as time


class CandlesAPI:
    def __init__(self, config):
        self.config = config
        self.store = pd.HDFStore('oanda_api_store.h5')

    def load(self, instrument, day, granularity):
        day_key = instrument + granularity + day.format('YYYYMMDD')
        if not day_key in self.store:  # True = reload

            if granularity == 'M5':
                values = self.load_day(day, granularity, "BA")
            elif granularity == 'S5' or granularity == 'S30':
                values = self.load_day_by_hour(day, granularity, "BA")

            day_ask_close = pd.Series(
                [float(candle['ask']['c']) for candle in values]).rename('ask_close')
            day_bid_close = pd.Series(
                [float(candle['bid']['c']) for candle in values]).rename('bid_close')
            day_ask_open = pd.Series(
                [float(candle['ask']['o']) for candle in values]).rename('ask_open')
            day_bid_open = pd.Series(
                [float(candle['bid']['o']) for candle in values]).rename('bid_open')
            day_ask_high = pd.Series(
                [float(candle['ask']['h']) for candle in values]).rename('ask_high')
            day_bid_high = pd.Series(
                [float(candle['bid']['h']) for candle in values]).rename('bid_high')
            day_ask_low = pd.Series(
                [float(candle['ask']['l']) for candle in values]).rename('ask_low')
            day_bid_low = pd.Series(
                [float(candle['bid']['l']) for candle in values]).rename('bid_low')
            #date_time = pd.Series(time.get(candle['time'],'YYYY-MM-DDTHH:mm:ss.SSSSSSSSZ').format('YYYYMMDDHHmmss') for candle in values).rename('date_time')
            time_of_day = pd.Series(int(time.get(candle['time'], 'YYYY-MM-DDTHH:mm:ss.SSSSSSSSZ').format(
                'HHmmss')) for candle in values).rename('time_of_day')
            signals = [
                # date_time,
                time_of_day,
                day_ask_open,
                day_bid_open,
                day_ask_close,
                day_bid_close,
                day_ask_high,
                day_bid_high,
                day_ask_low,
                day_bid_low
            ]

            raw_day = pd.concat(signals, axis=1).set_index('time_of_day')
            # TODO include time of day as HHMMss
            # TODO include day of week / week of year
            # TODO include some ta indicators
            self.store[day_key] = raw_day
            return raw_day
        else:
            raw_day = self.store[day_key]
            return raw_day

    def resample(self, signals):
        [signal for signal in signals if len(signal) > 128]
        sec_interval = 30
        steps = 24 * 60 * 2  # 2 for S30, 12 for S5
        steps = np.arange(steps)
        new_index = [int(start.shift(seconds=int(
            step * sec_interval)).format('HHmmss')) for step in steps]
        signals = [signal.reindex(new_index).fillna(
            method='backfill') for signal in signals]
        signals = signals[1:]
        return signals

    def load_day(self, instrument, day, granularity, price):
        time_format = 'YYYY-MM-DDTHH:mm:ssZ'
        base_uri = "https://api-fxpractice.oanda.com/v3/instruments/" +instrument+"/candles"
        headers = {"Authorization": self.config['token']}
        parameters = {
            "from": day.format(time_format),
            "to": day.shift(days=1).format(time_format),
            "price": price,
            "granularity": granularity,
            "includeFirst": "True",
        }
        response = http.get(base_uri, params=parameters,
                            headers=headers).json()
        # print(response)
        return response['candles']

    def load_day_by_hour(self, instrument, day, granularity, price):
        time_format = 'YYYY-MM-DDTHH:mm:ssZ'
        base_uri = "https://api-fxpractice.oanda.com/v3/instruments/" +instrument+"/candles"
        headers = {"Authorization": self.config['token']}
        start = day
        end = day.shift(days=1)
        hours = time.Arrow.range('hour', start, end)
        results = []
        for i in range(len(hours) - 1):
            hour = hours[i]
            # print(hour)
            parameters = {
                "from": hour.format(time_format),
                "to": hour.shift(hours=1).format(time_format),
                "price": price,
                "granularity": granularity,
                "includeFirst": "True",
            }
            response = http.get(base_uri, params=parameters,
                                headers=headers).json()
            # print(response)
            results.append(response['candles'])
        return [item for sublist in results for item in sublist]

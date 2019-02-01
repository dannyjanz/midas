import arrow as time
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from collections import deque
from oanda.preprocessing import add_indicators, denoise_frame, scale_frame
import ta


class DefaultRewardPolicy:
    def __init__(self):
        pass
    
    def calc_reward(self, account):
        reward = 0
        pl_sum = account.realized_pl + account.unrealized_pl
        
        if pl_sum > 0:
            reward = 1
        elif pl_sum <= 0:
            reward = -1
        
        return reward

    
class RealizedPLRewards:
    def __init__(self):
        pass

    def calc_reward(self, account):
        return account.realized_pl


class UnRealizedPLRewards:
    def __init__(self):
        pass

    def calc_reward(self, account):
        return account.unrealized_pl


class PLSumRewards:
    def __init__(self):
        pass

    def calc_reward(self, account):
        return account.unrealized_pl + account.realized_pl


class FinishedTradeRewards:
    def __init__(self):
        self.order_last_turn = None

    def calc_reward(self, account):
        reward = 0
        if self.order_last_turn is not None and account.current_order is None:
            reward = self.order_last_turn.profit_loss

        self.order_last_turn = account.current_order
        return reward
        

class FinishedTradeAccountBalance:
    def __init__(self):
        self.order_last_turn = None

    def calc_reward(self, account):
        reward = 0
        if self.order_last_turn is not None and account.current_order is None:
            reward = account.current_balance

        self.order_last_turn = account.current_order
        return reward 


class Same:
    def __init__(self, episodes):
        self.episodes = episodes

    def next_episode(self):
        pass


class OandaEnv:
    def __init__(self, api, window_size=32,
                 reward_policy=FinishedTradeAccountBalance(),
                 episode_policy=Same, verbose=False):

        self.api = api
        self.window_size = window_size
        self.dimensions = 8
        self.episodes = []
        self.raw_days = []
        self.reward_policy = reward_policy
        self.episode_index = 0

    def initialize(self, instrument='EUR_USD', granularity='M5', start=time.get("2018-01-02T00:00:00Z", 'YYYY-MM-DDTHH:mm:ss'), end=time.get("2018-02-02T00:00:00Z", 'YYYY-MM-DDTHH:mm:ss')):

        days = self.api.load_period(instrument, granularity, start, end)

        self.episodes = [add_indicators(episode) for episode in days]

    def next_episode(self):
        episode = Episode(self.episodes[self.episode_index], self.window_size, self.reward_policy)

        if self.episode_index < len(self.episodes) -1: 
            self.episode_index += 1
        else:
            self.episode_index = 0

        return episode

    def state_shape(self):
        return (self.window_size, self.dimensions)

    def action_dims(self):
        return 3


class Episode:
    def __init__(self, trading_data, win_size, reward_policy):
        print("new episode")
        self.actions = [0, 1, -1]
        self.action_functions = {1: self.buy, 0: self.hold, -1: self.sell}
        self.window_size = win_size
        self.current_step = 1
        self.trading_day = trading_data
        self.current_frame = self.trading_day[:self.window_size]
        self.account = Account(1000, 20)
        self.length = self.trading_day.shape[0] - self.window_size
        self.done = False
        self.reward_policy = reward_policy
        
        self.recent_actions = deque(np.zeros(win_size), win_size)
        self.recent_orders = deque(np.zeros(win_size), win_size)
        self.recent_upl = deque(np.zeros(win_size), win_size)
        self.recent_pl = deque(np.zeros(win_size), win_size)

    def step(self, action):
        assert action in self.actions
        assert not self.done
        
        self.action_functions[action]()
        self.current_step += 1
        
        self.recent_actions.append(action) #is this even advisable? 
        self.recent_orders.append(0 if self.account.current_order is None else self.account.current_order.order_type)
        self.recent_upl.append(self.account.unrealized_pl)
        self.recent_pl.append(self.account.realized_pl)

        next_frame = self.trading_day[self.current_step -1:self.window_size +
                                      self.current_step]
                                      
        self.current_frame = next_frame
        
        agent_frame = self.process_for_agent(next_frame)

        reward = self.reward_policy.calc_reward(self.account) # I need a better reward strategy, like positive PL = 1 negative pl = -1
        self.done = self.account.current_balance <= 0 or self.length - self.current_step == 0  # day / week is over or money is out
        return (agent_frame, reward, self.done)

    def process_for_agent(self, data):
        raw_signals = ['ask_close','bid_close','ask_high','bid_high','ask_low','bid_low']
        drop_signals = raw_signals + ['ask_open', 'bid_open', 'ema13', 'ema35']
        window_smooth = denoise_frame(data[raw_signals])
        window_smooth = window_smooth.diff()
        ema_diff = data[['ema13', 'ema35']].diff()
        window_x = pd.concat([data, window_smooth, ema_diff], axis=1).drop(drop_signals, axis=1).dropna()
        agent_frame = pd.concat([
            window_x,
            pd.Series(list(self.recent_actions), index=window_x.index).rename('actions'),
            pd.Series(list(self.recent_orders), index=window_x.index).rename('orders'),
            pd.Series(list(self.recent_upl), index=window_x.index).rename('unrealized'),
            pd.Series(list(self.recent_pl), index=window_x.index).rename('realized'),
        ], axis=1)
        window_x = scale_frame(window_x)
        return window_x

    def buy(self):
        self.account.place_order(self.current_frame.tail(1), 1)
        # print("buying!")

    def sell(self):
        self.account.place_order(self.current_frame.tail(1), -1)
        # print("selling!")

    def hold(self):
        self.account.update(self.current_frame.tail(1))
        # print("waiting..")


class Order:
    def __init__(self, order_type, market_info):
        self.close_price_function = {
            1: lambda frame: frame['ask_close'].values[0],
            -1: lambda frame: frame['bid_close'].values[0]
        }
        self.close_price = self.close_price_function[order_type]
        self.order_type = order_type
        self.order_price = self.close_price(market_info)
        self.initial_spread = market_info['ask_close'].values[0] - market_info['bid_close'].values[0]
        self.order_volume = 2000
        self.stop_loss = 0.0005
        self.take_profit = 0.0015
        self.profit_loss = self.calculate_pl(market_info)
        #print("order")

    def calculate_pl(self, market_info):
        return (((self.close_price(market_info) - self.order_price) *
                self.order_volume) * self.order_type) - self.initial_spread * self.order_volume

    def update(self, market_info):
        # TODO consider TP and SL
        self.profit_loss = self.calculate_pl(market_info)
        diff = self.close_price(market_info) - self.order_price
        if diff >= self.take_profit:  # TODO this is quite dirty, cap at the actual sl and tp & also consider high and low
            # print("katsching!")
            return (self.profit_loss, True)
        elif -diff >= self.stop_loss:
            # print("zonk!!!" + str(diff))
            return (self.profit_loss, True)
        else:
            # print("...")
            return (self.profit_loss, False)


class Account:
    def __init__(self, balance, leverage):
        self.initial_balance = balance
        self.current_balance = balance
        self.realized_pl = 0
        self.unrealized_pl = 0
        self.current_order = None
        # consider margin
        # print("account")

    def place_order(self, market_info, order_type):
        if self.current_order is None:
            self.current_order = Order(order_type, market_info)
            self.unrealized_pl = self.current_order.profit_loss
        elif self.current_order is not None and self.current_order.order_type == -order_type:
            self.current_order.update(market_info)
            self.realized_pl += self.current_order.profit_loss
            self.unrealized_pl = 0
            self.current_balance += self.current_order.profit_loss
            self.current_order = None
            # print("sold existing order")
        else:
            self.update(market_info)

    def update(self, market_info):
        if self.current_order != None:
            profit_loss, done = self.current_order.update(market_info)
            if done:
                self.realized_pl += profit_loss
                self.current_balance += profit_loss
                self.current_order = None
            else:
                self.unrealized_pl = profit_loss

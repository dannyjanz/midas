import arrow as time
import numpy as np
import pandas as pd
from collections import deque
from . preprocessing import add_indicators, denoise_frame, scale_frame
from . rewards import FinishedTradeRewards


class Same:
    def __init__(self, episodes):
        self.episodes = episodes

    def next_episode(self):
        pass


class OandaEnv:
    def __init__(self, api, window_size=32,
                 reward_policy=FinishedTradeRewards(),
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
        state = {}
        market_state = self.get_market_signal(data)
        
        state['market_state'] = scale_frame(market_state)
        
        env_state = pd.concat([
            pd.Series(list(self.recent_actions), index=market_state.index).rename('actions'),
            pd.Series(list(self.recent_orders), index=market_state.index).rename('orders'),
            pd.Series(list(self.recent_upl), index=market_state.index).rename('unrealized'),
            pd.Series(list(self.recent_pl), index=market_state.index).rename('realized'),
        ], axis=1)
        
        state['env_state'] = scale_frame(env_state)
        
        return state
        
    def get_market_signal(self, data):
        raw_signals = ['ask_close','bid_close','ask_high','bid_high','ask_low','bid_low','ask_open','bid_open']
        drop_signals = raw_signals + ['ema13', 'ema35']
        window_smooth = denoise_frame(data[raw_signals])
        window_smooth = window_smooth.diff()
        ema_diff = data[['ema13', 'ema35']].diff()
        window_x = pd.concat([data, window_smooth, ema_diff], axis=1).drop(drop_signals, axis=1).dropna()
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
        self.choose_functions(order_type)
        self.order_type = order_type
        self.order_price = self.close_price(market_info)
        self.initial_spread = market_info['ask_close'].values[0] - market_info['bid_close'].values[0]
        self.order_volume = 2000
        self.stop_loss = 0.0005
        self.take_profit = 0.0015
        self.profit_loss = self.calculate_pl(market_info)
        self.tp_dist = 0
        self.sl_dist = 0
        #print("order")
        
    def choose_functions(self, order_type):
        self.close_price_function = {
            1: lambda frame: frame['ask_close'].values[0],
            -1: lambda frame: frame['bid_close'].values[0]
        }
        self.high_price_function = {
            1: lambda frame: frame['ask_high'].values[0],
            -1: lambda frame: frame['bid_high'].values[0]
        }
        self.low_price_function = {
            1: lambda frame: frame['ask_low'].values[0],
            -1: lambda frame: frame['bid_low'].values[0]
        }
  
        self.close_price = self.close_price_function[order_type]
        self.high_price = self.high_price_function[order_type]
        self.low_price = self.low_price_function[order_type]
        
        tp_functions = {
            1: lambda market: (self.close_price(market) - self.order_price) >= self.take_profit or (self.high_price(market) - self.order_price) >= self.take_profit,
            -1: lambda market: - (self.close_price(market) - self.order_price) >= self.take_profit or - (self.low_price(market) - self.order_price) >= self.take_profit
        }
        
        sl_functions = {
            1: lambda market: - (self.close_price(market) - self.order_price) >= self.stop_loss or - (self.low_price(market) - self.order_price) >= self.stop_loss,
            -1: lambda market: (self.close_price(market) - self.order_price) >= self.stop_loss or (self.high_price(market) - self.order_price) >= self.stop_loss
        }
        
        self.hits_tp = tp_functions[order_type]
        self.hits_sl = sl_functions[order_type]

    def calculate_pl(self, market_info):
        return (((self.close_price(market_info) - self.order_price) *
                self.order_volume) * self.order_type) - self.initial_spread * self.order_volume
                

    def calculate_tp(self, market_info):
        return (self.take_profit * self.order_volume) - self.initial_spread * self.order_volume
        
    def calculate_sl(self, market_info):
        return -(self.stop_loss * self.order_volume) - self.initial_spread * self.order_volume
                
    def update(self, market_info):        
        # I should determine the distance if it doesnt hit.. and give it back to the bot
        
        if self.hits_tp(market_info):
            self.profit_loss = self.calculate_tp(market_info)
            return (self.profit_loss, True)
        elif self.hits_sl(market_info):
            self.profit_loss = self.calculate_sl(market_info)
            return (self.profit_loss, True)
        else:
            self.profit_loss = self.calculate_pl(market_info)
            return (self.profit_loss, False)


class Account:
    def __init__(self, balance, leverage):
        self.initial_balance = balance
        self.current_balance = balance
        self.realized_pl = 0
        self.unrealized_pl = 0
        self.current_order = None
        # TODO consider margin
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

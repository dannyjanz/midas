import arrow as time


class DefaultRewardPolicy:
    def __init__(self):
        pass
    
    def calc_reward(self, realized, unrealized):
        reward = 0
        
        if realized + unrealized > 0:
            reward = 1
        elif realized + unrealized < 0:
            reward = -1
        
        return reward

class OandaEnv:
    def __init__(self, api, window_size=32, reward_policy=DefaultRewardPolicy()):
        self.api = api
        self.window_size = window_size
        self.dimensions = 8
        self.episodes = []
        self.raw_days = []
        self.reward_policy = reward_policy

    def initialize(self):
        start = time.get("2018-01-02T00:00:00Z", 'YYYY-MM-DDTHH:mm:ss')
        end = time.get("2018-02-02T00:00:00Z", 'YYYY-MM-DDTHH:mm:ss')

        days = self.api.load_period('EUR_USD', start, end)

        self.episodes = [episode for episode in days if len(episode) > 128]

    def next_episode(self):
        return Episode(self.episodes[1], self.window_size, self.reward_policy)

    def state_shape(self):
        return (self.window_size, self.dimensions)

    def action_dims(self):
        return 3


class Episode:
    def __init__(self, trading_day, win_size, reward_policy):
        print("new episode")
        self.actions = [0, 1, -1]
        self.action_functions = {1: self.buy, 0: self.hold, -1: self.sell}
        self.window_size = win_size
        self.current_step = 0
        self.trading_day = trading_day
        self.current_frame = trading_day[:self.window_size]
        self.account = Account(1000, 20)
        self.length = trading_day.shape[0] - self.window_size
        self.done = False
        self.reward_policy = reward_policy

    def step(self, action):
        assert action in self.actions
        assert not self.done
        self.action_functions[action]()
        self.current_step += 1
        # TODO distinguish between raw frame for account usage and preprocessed frame for agent use
        next_frame = self.trading_day[self.current_step:self.window_size +
                                      self.current_step]
        self.current_frame = next_frame
        # should reward maybe only unrealiyed pl?
        reward = self.reward_policy.calc_reward(self.account.realized_pl, self.account.unrealized_pl) # I need a better reward strategy, like positive PL = 1 negative pl = -1
        self.done = self.account.current_balance <= 0 or self.length - self.current_step == 0  # day / week is over or money is out
        return (next_frame, reward, self.done)

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
        print("order")

    def calculate_pl(self, market_info):
        return (((self.close_price(market_info) - self.order_price) *
                self.order_volume) * self.order_type) - self.initial_spread * self.order_volume

    def update(self, market_info):
        # TODO consider TP and SL
        self.profit_loss = self.calculate_pl(market_info)
        diff = self.close_price(market_info) - self.order_price  # consider order type
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
        print("account")

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
            print("sold existing order")
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

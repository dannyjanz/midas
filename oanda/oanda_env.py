import arrow as time

class OandaEnv:
    def __init__(self, api):
        self.api = api
        self.episodes = []
        self.raw_days = []
        print("test")

    def initialize(self):
        start = time.get("2018-01-02T00:00:00Z", 'YYYY-MM-DDTHH:mm:ss')
        end = time.get("2018-02-02T00:00:00Z", 'YYYY-MM-DDTHH:mm:ss')

        days = self.api.load_period('EUR_USD', start, end)

        self.episodes = [
            episode for episode in days if len(episode) > 128]


    def next_episode(self):
        return Episode(self.episodes[1])


class Episode:
    def __init__(self, trading_day):
        print("new episode")
        self.actions = [0, 1, -1]
        self.action_functions = {
            1: self.buy,
            0: self.hold,
            -1: self.sell
        }
        self.window_size = 32
        self.current_step = 0
        self.trading_day = trading_day
        self.current_frame = trading_day[:self.window_size]
        self.account = Account(1000, 20)
        self.length = trading_day.shape[0] - self.window_size
        self.done = False

    def step(self, action):
        assert action in self.actions
        assert not self.done
        self.action_functions[action]()
        self.current_step += 1
        # TODO distinguish between raw frame for account usage and preprocessed frame for agent use
        next_frame = self.trading_day[self.current_step:
                                      self.window_size + self.current_step]
        self.current_frame = next_frame
        # should reward maybe only unrealiyed pl?
        reward = self.account.realized_pl + self.account.unrealized_pl
        self.done = self.account.current_balance <= 0 or self.length - \
            self.current_step == 0  # day / week is over or money is out
        print("next frame")
        return (next_frame, reward, self.done)

    def buy(self):
        self.account.place_order(self.current_frame.tail(1), 1)
        print("buying!")

    def sell(self):
        self.account.place_order(self.current_frame.tail(1), -1)
        print("selling!")

    def hold(self):
        self.account.update(self.current_frame.tail(1))
        print("waiting..")


class Order:
    def __init__(self, order_type, market_info):
        self.order_type = order_type
        # does the order type matter? fucking yes
        self.order_price = market_info['ask_close'].values[0]
        self.order_volume = 10000
        self.stop_loss = 0.00005
        self.take_profit = 0.00015  # 1.5pips?
        self.profit_loss = self.calculate_pl(market_info)
        print("order")

    def calculate_pl(self, market_info):
        # TODO is that right? or is the bid ask thingy reversed for a sell order?
        return ((market_info['bid'].values[0] - self.order_price) * self.order_volume) * self.order_type

    def update(self, market_info):
        # TODO consider TP and SL
        self.profit_loss = self.calculate_pl(market_info)
        diff = market_info['bid'].values[0] - \
            self.order_price  # consider order type
        if diff >= self.take_profit:  # todo this is quite dirty, cap at the actual sl and tp
            print("katsching!")
            return (self.profit_loss, True)
        elif -diff >= self.stop_loss:
            print("zonk!")
            return (self.profit_loss, True)
        else:
            print("...")
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
        if self.current_order == None:
            self.current_order = Order(order_type, market_info)
            self.unrealized_pl = self.current_order.profit_loss
        elif self.current_order != None and self.current_order.order_type == -order_type:
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


# ==========================================================================

def ema_crossings(emas):
    crossings = []
    prev_ema_fast = emas.iloc[0]['ema_fast']
    prev_ema_slow = emas.iloc[0]['ema_slow']
    for i in range(1, len(emas)):
        ema_fast = emas.iloc[i]['ema_fast']
        ema_slow = emas.iloc[i]['ema_slow']
        if prev_ema_fast > prev_ema_slow and ema_fast < ema_slow:
            crossings.append(-1)
        elif prev_ema_fast < prev_ema_slow and ema_fast > ema_slow:
            crossings.append(1)
        else:
            crossings.append(0)
        prev_ema_fast = ema_fast
        prev_ema_slow = ema_slow
    return crossings


def calc_chunks(data, crossings, pre_window):
    chunks = []
    last_cross = 0
    last_cross_index = 0
    for i in range(len(data)):
        if crossings[i] == -1:
            if last_cross == 1:
                chunks.append(Trade(
                    data[last_cross_index:i], 1, data[last_cross_index - pre_window:last_cross_index]))
            last_cross = -1
            last_cross_index = i
        elif crossings[i] == 1:
            if last_cross == -1:
                chunks.append(Trade(
                    data[last_cross_index:i], -1, data[last_cross_index - pre_window:last_cross_index]))
            last_cross = 1
            last_cross_index = i
    return chunks


class Trade():
    def __init__(self, frame, trade_type, pretrade=None):
        assert trade_type == 1 or trade_type == -1

        self.volume = 2000
        self.frame = frame
        self.trade_type = trade_type
        self.pretrade = pretrade

        self.open_price = frame['ask_close'].values[0] if trade_type == 1 else frame['bid_close'].values[0]
        self.close_price = frame['ask_close'].values[-1] if trade_type == 1 else frame['bid_close'].values[-1]
        self.diff = ((self.close_price - self.open_price)
                     * trade_type) * self.volume
        self.initial_spread = frame['ask_close'].values[0] - \
            frame['bid_close'].values[0]
        self.best = frame['bid_close'].max(
        ) if trade_type == 1 else frame['ask_close'].min()
        self.best_index = frame['bid_close'].idxmax(
        ) if trade_type == 1 else frame['ask_close'].idxmin()
        self.best_diff = abs(self.open_price - self.best)
        self.worst = frame['bid_close'].min(
        ) if trade_type == 1 else frame['ask_close'].max()
        self.worst_index = frame['bid_close'].idxmin(
        ) if trade_type == 1 else frame['ask_close'].idxmax()
        self.worst_diff = abs(self.open_price - self.worst)

        self.tp = 0.0009
        self.sl = 0.0003

        self.hit_tp_pos = None
        self.hit_sl_pos = None

        # TODO also check bid_high / low for potential TP/SL crossings
        if trade_type == 1:
            above_tp = frame[frame.bid_close > self.open_price + self.tp]
            below_sl = frame[frame.bid_close < self.open_price - self.sl]
        else:
            above_tp = frame[frame.ask_close < self.open_price - self.tp]
            below_sl = frame[frame.ask_close > self.open_price + self.sl]

        if len(above_tp) > 0:
            self.hit_tp_pos = above_tp.iloc[0].name
        if len(below_sl) > 0:
            self.hit_sl_pos = below_sl.iloc[0].name

        self.exit_reason = 'REVERSAL'
        self.realized = self.diff - self.initial_spread

        if self.hit_tp_pos != None and self.hit_sl_pos != None:
            if self.hit_tp_pos < self.hit_sl_pos:
                self.hits_tp()
            elif self.hit_sl_pos < self.hit_tp_pos:
                self.hits_sl()
        elif self.hit_tp_pos != None:
            self.hits_tp()
        elif self.hit_sl_pos != None:
            self.hits_sl()

    def hits_tp(self):
        self.realized = (self.tp - self.initial_spread) * self.volume
        self.exit_reason = 'TAKE PROFIT'

    def hits_sl(self):
        self.realized = ((self.sl + self.initial_spread) * self.volume) * -1
        self.exit_reason = 'STOP LOSS'

    def set_pretrade(self, pretrade):
        self.pretrade = pretrade

    def summary(self, plot_frame=False):
        print('-----------------------------------------------------')
        print('buy' if self.trade_type == 1 else 'sell')
        print('exit reason: ' + self.exit_reason)
        print('realized: ' + str(self.realized))
        print('diff: ' + str(self.diff))
        print('best: ' + str(self.best_diff))
        print('worst: ' + str(self.worst_diff))
        print(self.hit_tp_pos)
        print(self.hit_sl_pos)
        print('-----------------------------------------------------')
        if plot_frame:
            plt.plot(self.frame)
            plt.show()

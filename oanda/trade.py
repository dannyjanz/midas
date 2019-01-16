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
                chunks.append(
                    Trade(
                        data[last_cross_index:i], 1,
                        data[last_cross_index - pre_window:last_cross_index]))
            last_cross = -1
            last_cross_index = i
        elif crossings[i] == 1:
            if last_cross == -1:
                chunks.append(
                    Trade(
                        data[last_cross_index:i], -1,
                        data[last_cross_index - pre_window:last_cross_index]))
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

        self.open_price = frame['ask_close'].values[
            0] if trade_type == 1 else frame['bid_close'].values[0]
        self.close_price = frame['ask_close'].values[
            -1] if trade_type == 1 else frame['bid_close'].values[-1]
        self.diff = (
            (self.close_price - self.open_price) * trade_type) * self.volume
        self.initial_spread = frame['ask_close'].values[0] - frame['bid_close'].values[0]
        self.best = frame['bid_close'].max() if trade_type == 1 else frame[
            'ask_close'].min()
        self.best_index = frame['bid_close'].idxmax(
        ) if trade_type == 1 else frame['ask_close'].idxmin()
        self.best_diff = abs(self.open_price - self.best)
        self.worst = frame['bid_close'].min() if trade_type == 1 else frame[
            'ask_close'].max()
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
        print('buy' if self.trade_type == 1 else 'sssell')
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

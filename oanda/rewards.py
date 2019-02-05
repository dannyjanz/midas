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


class EasyTradeRewards:
    def __init__(self):
        self.order_last_turn = None

    def calc_reward(self, account):
        reward = 0
        if self.order_last_turn is not None and account.current_order is None:  # get pl after finished trade
            reward = self.order_last_turn.profit_loss
            reward = reward if reward > 0 else reward
        elif account.current_order is not None and self.order_last_turn is None:  # take off preasure of initial spread cost
            reward = 0 
        elif account.current_order is not None: # get upl from running position, discounted
            reward = account.current_order.profit_loss
            reward = reward * 0.1 if reward > 0 else reward * 0.1

        self.order_last_turn = account.current_order
        return reward
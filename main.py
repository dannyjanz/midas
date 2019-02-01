from oanda.oanda_candles_api import CandlesAPI
from oanda.oanda_env import OandaEnv
import arrow as time
import matplotlib.pyplot as plt

config = {
    'token': "Bearer ba610a6358dcb11c20dc2d923f8d255a-574912c7e0060d66b78ea02ad264802c",
}

start = time.get("2017-01-02T00:00:00Z", 'YYYY-MM-DDTHH:mm:ss')
end = time.get("2017-01-05T00:00:00Z", 'YYYY-MM-DDTHH:mm:ss')

class RealizedPLRewards:
    def __init__(self):
        pass
  
    def calc_reward(self, account):
        return account.realized_pl

api = CandlesAPI(config)
env = OandaEnv(api, reward_policy=RealizedPLRewards())
env.initialize()

for i in range(50):
    env.next_episode()

episode = env.next_episode()

next, reward, done = episode.step(-1)
print(reward)

for i in range(10):
    next, reward, done = episode.step(1)
    print(reward)
    print(next[0])
    
plt.plot(next)
plt.savefig('test.png')    

# print(next)
print(episode)

# signals = api.load_period('EUR_USD', start, end)
# print(signals)
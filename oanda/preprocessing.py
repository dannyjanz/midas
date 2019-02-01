from statsmodels.robust import mad
from sklearn.preprocessing import MinMaxScaler
import pywt
import numpy as np
import pandas as pd
import ta


def denoise(data, wavelet='bior6.8', level=1, mode='smooth'):
    coeff = pywt.wavedec(data, wavelet, mode=mode)
    sigma = mad(coeff[-level])
    uthresh = sigma * np.sqrt(2 * np.log(len(data)))
    coeff[1:] = (pywt.threshold(i, value=uthresh, mode="soft") for i in coeff[1:])
    y = pywt.waverec(coeff, wavelet, mode=mode)
    return y


def denoise_frame(data, wavelet='bior6.8'):
    smoothed_signals = []
    index = pd.Series(data.index).rename('time_of_day')
    smoothed_signals.append(index)
    for signal_name in data:
        signal = data[signal_name].values
        signal_smooth = denoise(signal, wavelet=wavelet)
        signal_smooth = pd.Series(signal_smooth).rename(signal_name + '_' + wavelet)
        smoothed_signals.append(signal_smooth)
    smoothed_frame = pd.concat(smoothed_signals, axis=1) 
    smoothed_frame = smoothed_frame.set_index('time_of_day')
    return smoothed_frame


def scale_frame(data):
    scaler = MinMaxScaler(feature_range=(0, 1))
    signals = []
    for signal_name in data:
        signal = data[signal_name].values
        signal = signal.reshape(-1,1).astype('float64')
        signal = scaler.fit_transform(signal)
        signals.append(signal)
    return np.concatenate(signals, axis=1)


def add_indicators(day):
    high = (day['ask_high'] + day['bid_high']) / 2
    high = high.rename('high')
    low = (day['ask_low'] + day['bid_low']) / 2
    low = low.rename('low')
    close = (day['ask_close'] + day['bid_close']) / 2
    close = close.rename('close')
    
    ao = ta.momentum.ao(high, low, s=13, l=35, fillna=False).rename('ao')
    rsi = ta.momentum.rsi(close, n=13, fillna=False).rename('rsi')
    atr = ta.volatility.average_true_range(high, low, close, n=13, fillna=False).rename('atr')
    ema13 = ta.trend.ema_indicator(close, n=13, fillna=False).rename('ema13')
    ema35 = ta.trend.ema_indicator(close, n=35, fillna=False).rename('ema35')
    all_data = pd.concat([day, ao, rsi, atr, ema13, ema35], axis=1)
    aligned_data = all_data.dropna()
    
    return aligned_data
    


    
def make_windows(data, window_size = 32, step_size = 16):
    raw_signals = ['ask_close','bid_close','ask_high','bid_high','ask_low','bid_low']
    drop_signals = raw_signals + ['ask_open', 'bid_open']
    data_x = []
    windowed_signals = []

    for i in range(len(enhanced_days)):
        signal = enhanced_days[i]
  
        for j in range(1, len(signal) - window_size, step_size):
            window_x = signal.iloc[j-1:j + window_size]
            window_smooth = denoise_frame(window_x[raw_signals])
            window_smooth_diff = window_smooth.diff()
            window_x = pd.concat([window_x, window_smooth_diff], axis=1).drop(drop_signals, axis=1).dropna()
    
            window_x = scale_frame(window_x)
            data_x.append(window_x)

    data_x = np.array(data_x)
    return data_x


def split(data_x):
    split_train = int(len(data_x) * 0.7)
    split_val = int(len(data_x) * 0.2) + split_train
    train_x = data_x[:split_train]
    test_x = data_x[split_train:split_val]
    val_x = data_x[split_val:]
    



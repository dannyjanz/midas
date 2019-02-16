from statsmodels.robust import mad
from sklearn.preprocessing import MinMaxScaler
import pywt
import numpy as np
import pandas as pd
import ta
from . constants import raw_signals, index_name

class DataPrep:
    def __init__(self, data):
        self.data = data

    def make_windows(self, window_size=32, step_size=16):
        denoiser = Denoiser()
        data_x = []
        windowed_signals = []

        # TODO add indicators

        for i in range(len(self.data)):
            signal = self.data[i]
      
            for j in range(1, len(signal) - window_size, step_size):
                window_x = signal.iloc[j-1:j + window_size]
                window_smooth = denoise_frame(window_x[raw_signals])
                window_smooth_diff = window_smooth.diff()
                window_x = pd.concat([window_x, window_smooth_diff], axis=1)
                window_x = window_x.drop(raw_signal, axis=1).dropna()
        
                window_x = scale_frame(window_x)
                data_x.append(window_x)
    
        data_x = np.array(data_x)
        return data_x
        
    
        
class Denoiser:
    def __init__(self, wavelet='bior6.8', mode='smooth', level=1):
        self.wavelet = wavelet
        self.mode = mode
        self.level = level
        pass
        
    def denoise_frame(self, data):
        smoothed_signals = []
        index = pd.Series(data.index).rename(index_name)
        smoothed_signals.append(index)
        for signal_name in data:
            signal = data[signal_name].values
            signal_smooth = denoise(signal)
            signal_smooth = pd.Series(signal_smooth).rename(signal_name + '_' + wavelet)
            smoothed_signals.append(signal_smooth)
        smoothed_frame = pd.concat(smoothed_signals, axis=1) 
        smoothed_frame = smoothed_frame.set_index('time_of_day')
        return smoothed_frame
    
    def denoise(self, data):
        coeff = pywt.wavedec(data, self.wavelet, mode=self.mode)
        sigma = mad(coeff[-self.level])
        uthresh = sigma * np.sqrt(2 * np.log(len(data)))
        coeff[1:] = (pywt.threshold(i, value=uthresh, mode="soft") for i in coeff[1:])
        y = pywt.waverec(coeff, wavelet, mode=mode)
        return y
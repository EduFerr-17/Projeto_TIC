import numpy as np
from scipy.signal import butter, filtfilt, find_peaks, savgol_filter
from datetime import datetime
import matplotlib.pyplot as plt

def Blood_Pressure(pressure_data, fs=100, plot=True):
    try:
        pressure_data = np.array(pressure_data)
        n_samples = len(pressure_data)
        t = np.arange(n_samples) / fs

        # --- Filtering Functions ---
        def butter_filter(data, cutoff, fs, order, btype):
            nyq = 0.5 * fs
            normal_cutoff = cutoff / nyq
            b, a = butter(order, normal_cutoff, btype=btype, analog=False)
            return filtfilt(b, a, data)

        # Step 1: Filtering
        cuff_pressure = butter_filter(pressure_data, cutoff=2, fs=fs, order=4, btype='low')
        oscillometric = butter_filter(cuff_pressure, cutoff=2, fs=fs, order=4, btype='high')

        # Step 2: Amplify and offset
        oscillometric *= 5
        oscillometric += abs(np.min(oscillometric))

        # Step 3: Smoothing
        def moving_average(signal, window_size=3):
            return np.convolve(signal, np.ones(window_size)/window_size, mode='same')

        oscillometric_smooth = moving_average(oscillometric, window_size=3)

        # Step 4: Envelope detection
        def envelope_detector(signal, frame=10):
            envelope = np.zeros_like(signal)
            for i in range(len(signal) - frame):
                max_val = np.max(signal[i:i+frame])
                if envelope[i] < max_val:
                    envelope[i] = envelope[i-1] + 0.1 * (max_val - envelope[i-1])
                else:
                    envelope[i] = envelope[i-1] - 0.1 * (envelope[i-1] - max_val)
            return envelope
        
        def envelope_from_peaks(signal):
            peaks, _ = find_peaks(signal, distance=fs*0.4)
            peak_vals = signal[peaks]
            envelope = np.interp(np.arange(len(signal)), peaks, peak_vals)
            return savgol_filter(envelope, 51, 3)  # smooth envelope

        envelope = envelope_from_peaks(oscillometric_smooth)

        #envelope = envelope_detector(oscillometric_smooth, frame=20)
        envelope = moving_average(envelope, window_size=3)

        # Step 5: MAP, SBP, DBP Estimation
        rs, rd = 0.5, 0.7
        yMAP = np.max(envelope)
        ysys, ydia = yMAP * rs, yMAP * rd
        xMAP = np.argmax(envelope)

        search_range = int(n_samples * 0.1)
        left = max(0, xMAP - search_range)
        right = min(n_samples, xMAP + search_range)

        xsys = left + np.argmin(np.abs(envelope[left:xMAP] - ysys))
        xdia = xMAP + np.argmin(np.abs(envelope[xMAP:right] - ydia))


        MAP = cuff_pressure[xMAP]
        SBP = cuff_pressure[xsys]
        DBP = cuff_pressure[xdia]

        # Pulse estimation
        peaks, _ = find_peaks(oscillometric_smooth, distance=fs * 0.5)
        if len(peaks) > 1:
            rr_intervals = np.diff(peaks) / fs
            avg_rr = np.mean(rr_intervals)
            pulse = int(60 / avg_rr)
        else:
            pulse = 0

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if plot:  # Plotting the results just for analysis 
            
            plt.figure(figsize=(12, 8))

            plt.subplot(3, 1, 1)
            plt.plot(t, pressure_data, label='Raw Pressure')
            plt.plot(t, cuff_pressure, label='Filtered Cuff Pressure', linewidth=2)
            plt.scatter([t[xsys], t[xdia], t[xMAP]], [SBP, DBP, MAP], 
                        color=['r','g','b'], label='SBP (red), DBP (green), MAP (blue)')
            plt.title("Cuff Pressure and Detected Points")
            plt.xlabel("Time (s)")
            plt.ylabel("Pressure (mmHg)")
            plt.legend()
            plt.grid(True)

            plt.subplot(3, 1, 2)
            plt.plot(t, oscillometric, label='Oscillometric Signal (highpass filtered)')
            plt.plot(t, oscillometric_smooth, label='Smoothed Oscillometric', linewidth=2)
            plt.title("Oscillometric Signal")
            plt.xlabel("Time (s)")
            plt.ylabel("Amplitude")
            plt.legend()
            plt.grid(True)

            plt.subplot(3, 1, 3)
            plt.plot(t, envelope, label='Envelope')
            plt.axhline(y=ysys, color='r', linestyle='--', label='Systolic threshold')
            plt.axhline(y=ydia, color='g', linestyle='--', label='Diastolic threshold')
            plt.scatter([t[xsys], t[xdia], t[xMAP]], [envelope[xsys], envelope[xdia], envelope[xMAP]], 
                        color=['r','g','b'], label='SBP, DBP, MAP Points')
            plt.title("Envelope Detection and Thresholds")
            plt.xlabel("Time (s)")
            plt.ylabel("Amplitude")
            plt.legend()    
            plt.grid(True)

            plt.tight_layout()
            plt.show()

        return round(SBP, 1), round(DBP, 1), pulse, timestamp

    except Exception as e:
        print(f"Error processing pressure data: {e}")
        return None, None, 0, None

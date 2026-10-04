from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import find_peaks, resample_poly
from math import gcd

ANALYSIS_VERSION = 'timbral-4'
RATE = 24000
MAX_SECONDS = 12

def load_audio(path, rate=RATE):
    with sf.SoundFile(str(path)) as f:
        sr, channels, duration = f.samplerate, f.channels, len(f) / f.samplerate
        # Bound decoder memory even for accidentally supplied field recordings.
        x = f.read(min(len(f), int(MAX_SECONDS * sr)), dtype='float32', always_2d=True)
    # Pick the strongest channel, avoiding cancellation of phase-inverted stereo.
    x = x[:, np.argmax(np.mean(x*x, axis=0))] if len(x) else np.zeros(1, np.float32)
    if not np.isfinite(x).all():
        raise ValueError('Audio contains non-finite values')
    if sr != rate:
        divisor = gcd(sr, rate)
        x = resample_poly(x, rate//divisor, sr//divisor).astype(np.float32)
    return x, {'duration': duration, 'sample_rate': sr, 'channels': channels}

def analyze(path):
    import librosa
    x, meta = load_audio(path)
    peak = float(np.max(np.abs(x)))
    if peak < 1e-6:
        return meta | dict(one_shot=0., drum_heuristic=0., features=[0.]*32,
                          detail={'reason':'silence', 'onsets':0})
    active = np.flatnonzero(np.abs(x) > peak * 0.005)
    leading = float(active[0]/RATE)
    x = x[active[0]:active[-1]+1]
    active_duration = len(x)/RATE
    x = x / peak
    frame = 240
    padded = np.pad(x, (0, (-len(x)) % frame))
    env = np.sqrt(np.mean(padded.reshape(-1, frame)**2, axis=1))
    # Separate bursts count even when the first onset is at the file boundary.
    padded_env = np.r_[0, env, 0]
    peaks, _ = find_peaks(padded_env, prominence=max(env.max()*.22, .01), distance=8)
    onsets = max(1, len(peaks))
    tail = float(np.mean(env[-max(1,len(env)//5):]) / (env.max()+1e-8))
    attack = float(np.argmax(env)*.01)
    MAX_ONE_SHOT_SECONDS = 6.0
    duration_score = 1.0 if active_duration <= MAX_ONE_SHOT_SECONDS else 0.0
    # Long files stay rejected even if the first decoded section resembles a hit.
    if meta['duration'] > MAX_SECONDS:
        duration_score = 0.
    one_shot = float(duration_score * np.exp(-.8*(onsets-1)) *
                     (.45+.55*(1-np.clip(tail,0,1))) * np.exp(-max(0,attack-.12)*2))
    y = np.pad(x, (0,max(0,2048-len(x))))
    spectrum = np.abs(librosa.stft(y, n_fft=1024, hop_length=256)) + 1e-9
    weights = spectrum.sum(axis=0)
    def avg(v): return float(np.average(v.ravel(),weights=weights))
    centroid = avg(librosa.feature.spectral_centroid(S=spectrum,sr=RATE))
    bandwidth = avg(librosa.feature.spectral_bandwidth(S=spectrum,sr=RATE))
    rolloff = avg(librosa.feature.spectral_rolloff(S=spectrum,sr=RATE))
    flatness = avg(librosa.feature.spectral_flatness(S=spectrum))
    zcr = float(np.mean(librosa.feature.zero_crossing_rate(y,frame_length=1024,hop_length=256)))
    mel = librosa.feature.melspectrogram(S=spectrum**2,sr=RATE,n_mels=40)
    mfcc = librosa.feature.mfcc(S=librosa.power_to_db(mel),n_mfcc=13)[1:13]
    # 24 MFCC moments + 8 interpretable timbral/envelope features = 32 dimensions.
    features = np.r_[mfcc.mean(axis=1), mfcc.std(axis=1),
                     np.log1p([centroid,bandwidth,rolloff]),flatness,zcr,
                     np.log1p(active_duration), attack, tail]
    drum = float(np.clip(.30 + .4*(1-tail) + .2*np.exp(-attack*12) + .1*min(1,flatness*10),0,1))
    return meta | dict(one_shot=one_shot,drum_heuristic=drum,
                      features=features.tolist(),detail={'onsets':onsets,'tail_ratio':tail,
                      'attack_seconds':attack,'active_duration':active_duration,'leading_silence':leading,
                      'centroid_hz':centroid,'reason':'envelope heuristic'})

class ClapEmbedder:
    MODEL = 'laion/clap-htsat-unfused'
    REVISION = '8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a'
    VERSION = MODEL + ':' + REVISION + ':trim-repeatpad-v1'
    POSITIVE = ['The sound of a kick drum.', 'The sound of a snare drum.',
                'The sound of a hi hat or cymbal.', 'The sound of a tom drum.',
                'The sound of a hand clap.', 'The sound of a percussion instrument being struck.']
    NEGATIVE = ['The sound of a person speaking or singing.', 'The sound of a guitar note.',
                'The sound of a piano note.', 'The sound of a sustained synthesizer or bass note.',
                'The sound of ambient nature or traffic.', 'The sound of a string or wind instrument.']
    def __init__(self, cache_dir):
        import torch
        from transformers import ClapModel, ClapProcessor
        self.torch = torch
        torch.set_num_threads(min(4, torch.get_num_threads()))
        self.processor = ClapProcessor.from_pretrained(self.MODEL, revision=self.REVISION, cache_dir=cache_dir)
        self.model = ClapModel.from_pretrained(self.MODEL, revision=self.REVISION, cache_dir=cache_dir, use_safetensors=False).eval()
        prompts = self.POSITIVE + self.NEGATIVE
        with torch.inference_mode():
            self.text = self.model.get_text_features(**self.processor(text=prompts, return_tensors='pt',padding=True))
            self.text = torch.nn.functional.normalize(self.text,dim=-1)
    def embed(self,path):
        x, _ = load_audio(path,48000)
        peak = np.max(np.abs(x))
        active = np.flatnonzero(np.abs(x)>max(peak*.005,1e-7))
        if len(active): x=x[active[0]:active[-1]+1]
        x=x/max(peak,1e-7)*.9
        inputs=self.processor(audios=x,sampling_rate=48000,return_tensors='pt',padding='repeatpad')
        with self.torch.inference_mode():
            v=self.model.get_audio_features(**inputs)
            v=self.torch.nn.functional.normalize(v,dim=-1)
            sims=(v @ self.text.T)[0].cpu().numpy()
        # Max-to-max avoids counting prompt categories as independent evidence.
        margin=float(sims[:6].max()-sims[6:].max())
        score=float(1/(1+np.exp(-margin/.07)))
        label=(self.POSITIVE+self.NEGATIVE)[int(sims.argmax())]
        return v[0].cpu().numpy(),score,{'prompt':label,'margin':margin}

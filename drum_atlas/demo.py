from pathlib import Path
import numpy as np
import soundfile as sf

def generate(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(42);sr=24000;t=np.arange(sr)/sr
    for i in range(6):
        kick=np.sin(2*np.pi*((45+i*5)*t+10*(1-np.exp(-t*30))))*np.exp(-t*(7+i))
        snare=(.6*rng.normal(size=len(t))+.4*np.sin(2*np.pi*(180+i*20)*t))*np.exp(-t*(15+i))
        noise=rng.normal(size=len(t));hat=np.diff(noise,prepend=0)*np.exp(-t*(25+i*4))
        for label,x in [('kick',kick),('snare',snare),('hat',hat)]:
            sf.write(root/f'{label}_{i}.wav',x/max(np.max(np.abs(x)),1)*.8,sr)
    loop=np.zeros(sr*4)
    for offset in range(0,len(loop),sr//2):loop[offset:offset+sr//3]+=kick[:sr//3]
    sf.write(root/'loop.wav',loop,sr)
    sf.write(root/'sustained_tone.wav',.5*np.sin(2*np.pi*440*np.arange(sr*4)/sr),sr)
    sf.write(root/'silence.wav',np.zeros(sr),sr)

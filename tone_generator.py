#!/usr/bin/env python3
import numpy as np
import simpleaudio as sa

def generate_tone(frequency=440, duration=1, sample_rate=44100):
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    tone = 0.5 * np.sin(2 * np.pi * frequency * t)
    audio = np.int16(tone * 32767)
    return audio

def main():
    audio = generate_tone()
    play_obj = sa.play_buffer(audio, 1, 2, 44100)
    play_obj.wait_done()

if __name__ == "__main__":
    main()
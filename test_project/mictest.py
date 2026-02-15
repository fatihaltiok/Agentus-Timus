import sounddevice as sd
import numpy as np

print("Verfügbare Geräte:")
print(sd.query_devices())
print(f"\nStandard-Eingabe: {sd.default.device[0]}")

print("\n🎤 Teste Mikrofon (3 Sekunden)...")
audio = sd.rec(int(3 * 16000), samplerate=16000, channels=1, dtype='float32')
sd.wait()

volume = np.abs(audio).mean()
max_vol = np.abs(audio).max()

print(f"Durchschnitt: {volume:.6f}")
print(f"Maximum: {max_vol:.6f}")

if max_vol < 0.001:
    print("❌ Kein Signal - Mikrofon nicht aktiv oder falsch!")
elif max_vol < 0.01:
    print("⚠️ Sehr leises Signal - Schwellwert anpassen")
else:
    print("✅ Mikrofon funktioniert!")
import torchaudio as ta
from chatterbox.tts import ChatterboxTTS

model = ChatterboxTTS.from_pretrained(device="cuda")

wav = model.generate(
    "Hey there! I'm testing Chatterbox to see how it sounds.",
    audio_prompt_path="reference_voice.wav"
)
ta.save("output_chatterbox.wav", wav, model.sr)
print("Done! Check output_chatterbox.wav")
from TTS.api import TTS

tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")

tts.tts_to_file(
    text="hey thats a test #1 for aliy",
    speaker_wav="reference_voice.wav",
    language="en",
    file_path="output.wav"
)

print("Done!! check output.wav")